import os, tempfile
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
from fastapi.testclient import TestClient
from .main import app

c = TestClient(app)
H = {"X-Token": c.post("/api/login", json={"username": "AdminRMZDS", "password": "A:2026*"}).json()["token"]}
emp = lambda no, dept: c.post("/api/employees", headers=H, json={"emp_no": no, "name": "N" + no, "position": "P", "basic_monthly": 25000, "department_id": dept})

def test_delete_flow():
    assert c.post("/api/departments", headers=H, json={"name": "Treasury"}).status_code == 200
    emp("1", 1); emp("2", 1)
    assert c.delete("/api/departments/1", headers=H).status_code == 409      # still has employees
    assert c.post("/api/payroll/run", headers=H, json={"period": "2026-10"}).status_code == 200
    assert c.delete("/api/employees/1", headers=H).json()["result"] == "archived"   # has payslips
    emp("3", 1)
    assert c.delete("/api/employees/3", headers=H).json()["result"] == "deleted"    # no payslips
    assert c.delete("/api/employees/2", headers=H).json()["result"] == "archived"
    assert c.delete("/api/departments/1", headers=H).status_code == 200
    assert c.get("/api/employees", headers=H).json() == []
    assert emp("1", None).status_code == 200                                 # number reusable after archive
    assert c.get("/api/payroll/2026-10", headers=H).json()["payslips"][0]["department"] == "Treasury"  # history kept
