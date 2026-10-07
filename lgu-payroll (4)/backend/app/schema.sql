-- Municipal Payroll database (SQLite). Safe to run many times.
CREATE TABLE IF NOT EXISTS departments(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS employees(
  id INTEGER PRIMARY KEY, emp_no TEXT NOT NULL UNIQUE, name TEXT NOT NULL, position TEXT,
  basic_monthly REAL NOT NULL, allowance REAL DEFAULT 2000, active INTEGER DEFAULT 1,
  department_id INTEGER REFERENCES departments(id));
CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY, period TEXT NOT NULL UNIQUE, status TEXT NOT NULL, created_by TEXT, approved_by TEXT);
CREATE TABLE IF NOT EXISTS payslips(
  id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(id),
  employee_id INTEGER NOT NULL REFERENCES employees(id), data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(
  ts TEXT DEFAULT CURRENT_TIMESTAMP, actor TEXT, action TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS users(
  username TEXT PRIMARY KEY, pw_hash TEXT NOT NULL, role TEXT NOT NULL, must_change INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY, username TEXT NOT NULL, expires REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_emp_dept ON employees(department_id);
CREATE INDEX IF NOT EXISTS idx_slip_run ON payslips(run_id);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit(ts);
