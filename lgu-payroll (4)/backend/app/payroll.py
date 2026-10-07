"""Payroll engine for a Philippine LGU (monthly). Rates are ASSUMPTIONS: verify with GSIS, PhilHealth, Pag-IBIG and BIR before real use."""
from decimal import Decimal as D, ROUND_HALF_UP

def r(x): return D(x).quantize(D("0.01"), ROUND_HALF_UP)

def gsis(basic): return r(D(basic) * D("0.09"))                      # employee share 9%
def philhealth(basic):                                               # 5% premium, split 50/50, floor 10k, cap 100k
    return r(min(max(D(basic), D(10000)), D(100000)) * D("0.05") / 2)
def pagibig(basic): return r(min(D(basic), D(10000)) * D("0.02"))    # 2% of max 10k

# TRAIN monthly withholding: (lower bound, fixed tax, rate on excess)
BRACKETS = [(D(0), D(0), D(0)), (D(20833), D(0), D("0.15")), (D(33333), D("1875"), D("0.20")),
            (D(66667), D("8541.80"), D("0.25")), (D(166667), D("33541.80"), D("0.30")),
            (D(666667), D("183541.80"), D("0.35"))]

def withholding_tax(taxable):
    taxable = D(taxable)
    lower, base, rate = [b for b in BRACKETS if taxable > b[0] or b[0] == 0][-1]
    return r(base + (taxable - lower) * rate)

def compute(basic, allowance=0, absent_days=0, overtime=0, other_deductions=0, work_days=22):
    basic, allowance, overtime = D(basic), D(allowance), D(overtime)
    absence = r(basic / work_days * D(absent_days))
    earned = basic - absence
    gross = r(earned + allowance + overtime)
    g, ph, pi = gsis(basic), philhealth(basic), pagibig(basic)
    taxable = max(D(0), earned + overtime - g - ph - pi)             # allowance (PERA) treated as non-taxable
    tax = withholding_tax(taxable)
    deductions = r(g + ph + pi + tax + D(other_deductions))
    return {"basic": str(r(basic)), "absence": str(absence), "allowance": str(r(allowance)), "overtime": str(r(overtime)),
            "gross": str(gross), "gsis": str(g), "philhealth": str(ph), "pagibig": str(pi), "tax": str(tax),
            "other": str(r(other_deductions)), "total_deductions": str(deductions), "net": str(r(gross - deductions))}
