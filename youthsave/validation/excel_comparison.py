"""
One-time (or on-demand) validation harness: confirms the Python engine
reproduces YouthSave_Plan.xlsx exactly for the base-case illustration
(entry age 20, term 10, both plans, both genders -- the only scenario
the source workbook actually contains, since it's a fixed 10-year
illustration rather than a general-term model).

This script is NOT a runtime dependency of the engine. Nothing in
engine/ or analysis/ imports openpyxl or reads the .xlsx file -- only
this script does. Run it once after any change to engine/ that could
plausibly affect the numbers; once it passes, the Excel file is no
longer needed for the model to function.

Usage:
    python validation/excel_comparison.py /path/to/YouthSave_Plan.xlsx

Tolerance: 1e-6 absolute difference. Everything validated in this
project's build sessions matched to ~1e-9 to ~1e-13 (floating-point
noise), so 1e-6 is deliberately loose -- a genuine model discrepancy
will blow past it by orders of magnitude, not sit near the boundary.
"""

import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.config import load_assumptions, load_plan_specs
from engine.decrements import (
    load_mortality_disability, load_surrender, build_decrement_table, add_waiver_table,
)
from engine.pricing import solve_premium
from engine.profit_testing import price_and_test
from analysis.sensitivity import run_sensitivity

TOLERANCE = 1e-6

# Cell references pulled directly from YouthSave_Plan.xlsx during model
# construction -- see conversation history / commit messages for how
# each was located. MALE uses rows 6-25 (Plan A) / 6-15 (Plan B pricing);
# FEMALE uses the mirrored columns/rows on the same sheets.
EXCEL_REFERENCES = {
    "plan_a": {
        "M": {"premium_cell": ("Pricing_Plan_A", "K2"), "npv_cell": ("Profit_testing_Plan_A", "E38"),
              "pv_prem_cell": ("Profit_testing_Plan_A", "F38"), "margin_cell": ("Profit_testing_Plan_A", "B39")},
        "F": {"premium_cell": ("Pricing_Plan_A", "K23")},
    },
    "plan_b": {
        "M": {"premium_cell": ("Pricing_Plan_B", "K2")},
        "F": {"premium_cell": ("Pricing_Plan_B", "K23")},
    },
}


class ValidationReport:
    def __init__(self):
        self.results = []

    def check(self, label, python_value, excel_value, tol=TOLERANCE):
        diff = abs(python_value - excel_value)
        passed = diff <= tol
        self.results.append((label, python_value, excel_value, diff, passed))
        return passed

    def print_summary(self):
        print(f"{'Check':<55}{'Python':>18}{'Excel':>18}{'Diff':>14}  Status")
        print("-" * 115)
        n_pass = 0
        for label, py, xl, diff, passed in self.results:
            status = "PASS" if passed else "FAIL"
            n_pass += passed
            print(f"{label:<55}{py:>18.6f}{xl:>18.6f}{diff:>14.2e}  {status}")
        print("-" * 115)
        print(f"{n_pass}/{len(self.results)} checks passed.")
        return n_pass == len(self.results)


def validate(xlsx_path: str):
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    report = ValidationReport()

    from engine.config import load_term_rates, assumptions_for_term
    base_assumptions = load_assumptions()
    term_rates = load_term_rates()
    plans = load_plan_specs(assumptions=base_assumptions)
    mort = load_mortality_disability()
    surr = load_surrender()

    entry_age, term = 20, 10
    assumptions = assumptions_for_term(base_assumptions, term, term_rates)  # Excel's base case is term=10

    for plan_key in ["plan_a", "plan_b"]:
        for gender in ["M", "F"]:
            plan = plans[plan_key]
            table = build_decrement_table(entry_age, term, gender, mort, surr)
            if plan_key == "plan_b":
                table = add_waiver_table(table, mort, plan.waived_mortality_loading, assumptions.pricing_interest_rate)
            premium = solve_premium(table, assumptions, plan)

            sheet, cell = EXCEL_REFERENCES[plan_key][gender]["premium_cell"]
            excel_premium = wb[sheet][cell].value
            report.check(f"{plan_key} {gender} premium", premium, excel_premium)

            if plan_key == "plan_a" and gender == "M":
                result = price_and_test(table, assumptions, plan, premium, plan_key)
                sheet, cell = EXCEL_REFERENCES["plan_a"]["M"]["npv_cell"]
                report.check("plan_a M NPV", result.npv, wb[sheet][cell].value)
                sheet, cell = EXCEL_REFERENCES["plan_a"]["M"]["pv_prem_cell"]
                report.check("plan_a M PV premiums", result.pv_premiums_total, wb[sheet][cell].value)
                sheet, cell = EXCEL_REFERENCES["plan_a"]["M"]["margin_cell"]
                report.check("plan_a M profit margin", result.profit_margin, wb[sheet][cell].value)

    # Sensitivity spot-checks: Pricing Interest Rate (repricing case) and
    # Withdrawal Charge (the linkage fix), Plan A male, both directions.
    _, rows = run_sensitivity(entry_age, term, "M", "plan_a", plans["plan_a"], assumptions, mort, surr)
    excel_sensitivity = {
        ("Pricing Interest Rate", "+"): 0.08559773022257346,
        ("Pricing Interest Rate", "-"): 0.19807778250331556,
        ("Withdrawal Charge", "+"): 0.15210856515534432,
        ("Withdrawal Charge", "-"): 0.15114037901639785,
    }
    for r in rows:
        key = (r["assumption"], r["direction"])
        if key in excel_sensitivity:
            report.check(f"sensitivity: {key[0]} ({key[1]})", r["stressed_margin"], excel_sensitivity[key])

    return report.print_summary()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python validation/excel_comparison.py /path/to/YouthSave_Plan.xlsx")
        sys.exit(1)
    all_passed = validate(sys.argv[1])
    sys.exit(0 if all_passed else 1)
