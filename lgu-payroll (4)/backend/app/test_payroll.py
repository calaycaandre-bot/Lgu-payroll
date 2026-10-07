from decimal import Decimal as D
from .payroll import compute, withholding_tax, philhealth, pagibig

def test_low_salary_no_tax():
    assert withholding_tax(20000) == D("0.00")

def test_bracket_20_percent():
    assert withholding_tax(40000) == D("3208.40")  # 1875 + 6667 * 0.20

def test_philhealth_floor_and_cap():
    assert philhealth(5000) == D("250.00")
    assert philhealth(200000) == D("2500.00")

def test_pagibig_cap():
    assert pagibig(50000) == D("200.00")

def test_net_is_gross_minus_deductions():
    p = compute(30000, allowance=2000, absent_days=1)
    assert D(p["net"]) == D(p["gross"]) - D(p["total_deductions"])
