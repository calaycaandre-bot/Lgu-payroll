import json, os, secrets, sqlite3, time
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .payroll import compute
from .security import hash_pw, check_pw

DB = os.getenv("DB_PATH", "payroll.db")
SESSION_SECONDS = 8 * 3600
FAILS = {}   # username -> [count, first_failure_time]

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c

with db() as c:
    c.executescript((Path(__file__).parent / "schema.sql").read_text())   # tables live in schema.sql
    try: c.execute("ALTER TABLE employees ADD COLUMN department_id INTEGER")   # upgrade older databases
    except sqlite3.OperationalError: pass
    ADMIN = os.getenv("ADMIN_USER", "AdminRMZDS")
    c.execute("DELETE FROM users WHERE username<>?", (ADMIN,))          # the admin is the only account that can sign in
    c.execute("DELETE FROM sessions WHERE username<>?", (ADMIN,))
    if not c.execute("SELECT 1 FROM users WHERE username=?", (ADMIN,)).fetchone():
        c.execute("INSERT INTO users VALUES(?,?,?,0)", (ADMIN, hash_pw(os.getenv("ADMIN_PASS", "A:2026*")), "admin"))

app = FastAPI(title="LGU Payroll")

def auth(token, *roles, allow_change=False):
    with db() as c:
        row = c.execute("SELECT u.* FROM sessions s JOIN users u ON u.username=s.username WHERE s.token=? AND s.expires>?",
                        (token, time.time())).fetchone()
    if not row: raise HTTPException(401, "Please sign in")
    if row["must_change"] and not allow_change: raise HTTPException(403, "Change your starter password first")
    if roles and row["role"] != "admin" and row["role"] not in roles: raise HTTPException(403, f"This action needs the role: {' or '.join(roles)}")
    return row

def log(actor, action, detail=""):
    with db() as c: c.execute("INSERT INTO audit(actor,action,detail) VALUES(?,?,?)", (actor, action, detail))

class Login(BaseModel): username: str; password: str
class NewPass(BaseModel): old: str; new: str
class Dept(BaseModel): name: str
class Emp(BaseModel):
    emp_no: str; name: str; position: str; basic_monthly: float; allowance: float = 2000; department_id: int | None = None
class Run(BaseModel):
    period: str
    absences: dict[int, float] = {}

@app.get("/health")
def health(): return {"ok": True}

@app.post("/api/login")
def login(b: Login, request: Request):
    b.username = b.username.strip()
    key = (request.client.host if request.client else "?", b.username)   # lock per device, so a phone's typos don't lock the laptop
    n, t0 = FAILS.get(key, [0, time.time()])
    if n >= 5 and time.time() - t0 < 300: raise HTTPException(429, "Too many attempts. Wait 5 minutes.")
    with db() as c: u = c.execute("SELECT * FROM users WHERE username=?", (b.username,)).fetchone()
    if not u or not check_pw(b.password, u["pw_hash"]):
        FAILS[key] = [n + 1 if time.time() - t0 < 300 else 1, t0 if time.time() - t0 < 300 else time.time()]
        log(b.username, "login_failed"); raise HTTPException(401, "Wrong username or password")
    FAILS.pop(key, None)
    tok = secrets.token_urlsafe(32)
    with db() as c: c.execute("INSERT INTO sessions VALUES(?,?,?)", (tok, u["username"], time.time() + SESSION_SECONDS))
    log(u["username"], "login")
    return {"token": tok, "username": u["username"], "role": u["role"], "must_change": bool(u["must_change"])}

@app.post("/api/logout")
def logout(x_token: str = Header("")):
    with db() as c: c.execute("DELETE FROM sessions WHERE token=?", (x_token,))
    return {"ok": True}

@app.post("/api/password")
def change_password(b: NewPass, x_token: str = Header("")):
    u = auth(x_token, allow_change=True)
    if not check_pw(b.old, u["pw_hash"]): raise HTTPException(400, "Current password is wrong")
    if len(b.new) < 8 or b.new == b.old: raise HTTPException(400, "New password needs 8+ characters and must be different")
    with db() as c: c.execute("UPDATE users SET pw_hash=?, must_change=0 WHERE username=?", (hash_pw(b.new), u["username"]))
    log(u["username"], "change_password"); return {"ok": True}

@app.get("/api/departments")
def departments(x_token: str = Header("")):
    auth(x_token)
    with db() as c: return [dict(r) for r in c.execute("SELECT * FROM departments ORDER BY name")]

@app.post("/api/departments")
def add_department(b: Dept, x_token: str = Header("")):
    u = auth(x_token, "hr")
    if not b.name.strip(): raise HTTPException(400, "Department name is required")
    try:
        with db() as c: c.execute("INSERT INTO departments(name) VALUES(?)", (b.name.strip(),))
    except sqlite3.IntegrityError: raise HTTPException(409, "Department already exists")
    log(u["username"], "add_department", b.name); return {"ok": True}

@app.get("/api/employees")
def employees(x_token: str = Header("")):
    auth(x_token)
    with db() as c:
        return [dict(r) for r in c.execute("""SELECT e.*, d.name AS department FROM employees e
                 LEFT JOIN departments d ON d.id=e.department_id WHERE e.active=1 ORDER BY e.name""")]

@app.post("/api/employees")
def add_employee(e: Emp, x_token: str = Header("")):
    u = auth(x_token, "hr")
    try:
        with db() as c: c.execute("INSERT INTO employees(emp_no,name,position,basic_monthly,allowance,department_id) VALUES(?,?,?,?,?,?)",
                                  (e.emp_no, e.name, e.position, e.basic_monthly, e.allowance, e.department_id))
    except sqlite3.IntegrityError: raise HTTPException(409, "Employee number already exists")
    log(u["username"], "add_employee", e.emp_no); return {"ok": True}

@app.delete("/api/employees/{emp_id}")
def delete_employee(emp_id: int, x_token: str = Header("")):
    u = auth(x_token, "hr")
    with db() as c:
        e = c.execute("SELECT * FROM employees WHERE id=?", (emp_id,)).fetchone()
        if not e: raise HTTPException(404, "Employee not found")
        if c.execute("SELECT 1 FROM payslips WHERE employee_id=?", (emp_id,)).fetchone():
            # has payroll history: archive instead of erasing, so past payslips stay correct
            c.execute("UPDATE employees SET active=0, emp_no=emp_no||'~archived'||id WHERE id=?", (emp_id,))
            result = "archived"
        else:
            c.execute("DELETE FROM employees WHERE id=?", (emp_id,)); result = "deleted"
    log(u["username"], "delete_employee", f"{e['emp_no']} {result}"); return {"result": result}

@app.delete("/api/departments/{dept_id}")
def delete_department(dept_id: int, x_token: str = Header("")):
    u = auth(x_token, "hr")
    with db() as c:
        d = c.execute("SELECT * FROM departments WHERE id=?", (dept_id,)).fetchone()
        if not d: raise HTTPException(404, "Department not found")
        n = c.execute("SELECT COUNT(*) FROM employees WHERE department_id=? AND active=1", (dept_id,)).fetchone()[0]
        if n: raise HTTPException(409, f"{n} employee(s) still belong to this department. Move or delete them first.")
        c.execute("UPDATE employees SET department_id=NULL WHERE department_id=?", (dept_id,))
        c.execute("DELETE FROM departments WHERE id=?", (dept_id,))
    log(u["username"], "delete_department", d["name"]); return {"result": "deleted"}

@app.post("/api/payroll/run")
def run_payroll(body: Run, x_token: str = Header("")):
    u = auth(x_token, "accounting")
    with db() as c:
        if c.execute("SELECT 1 FROM runs WHERE period=?", (body.period,)).fetchone():
            raise HTTPException(409, "Payroll for this period already exists")
        rid = c.execute("INSERT INTO runs(period,status,created_by) VALUES(?,?,?)", (body.period, "draft", u["username"])).lastrowid
        for e in c.execute("""SELECT e.*, d.name AS dept FROM employees e LEFT JOIN departments d ON d.id=e.department_id
                              WHERE e.active=1""").fetchall():
            p = compute(e["basic_monthly"], e["allowance"], body.absences.get(e["id"], 0))
            c.execute("INSERT INTO payslips(run_id,employee_id,data) VALUES(?,?,?)",
                      (rid, e["id"], json.dumps({**p, "name": e["name"], "emp_no": e["emp_no"], "department": e["dept"] or "Unassigned"})))
    log(u["username"], "run_payroll", body.period); return {"run_id": rid, "status": "draft"}

@app.get("/api/payroll/{period}")
def get_payroll(period: str, x_token: str = Header("")):
    auth(x_token)
    with db() as c:
        run = c.execute("SELECT * FROM runs WHERE period=?", (period,)).fetchone()
        if not run: raise HTTPException(404, "No payroll for this period")
        slips = [json.loads(r["data"]) for r in c.execute("SELECT data FROM payslips WHERE run_id=?", (run["id"],))]
    return {"period": period, "status": run["status"], "payslips": slips}

@app.post("/api/payroll/{period}/approve")
def approve(period: str, x_token: str = Header("")):
    u = auth(x_token, "treasurer")
    with db() as c:
        n = c.execute("UPDATE runs SET status='approved', approved_by=? WHERE period=? AND status='draft'", (u["username"], period)).rowcount
    if not n: raise HTTPException(409, "Nothing to approve (missing or already approved)")
    log(u["username"], "approve_payroll", period); return {"status": "approved"}

app.mount("/", StaticFiles(directory=Path(__file__).resolve().parents[2] / "frontend", html=True), name="ui")
