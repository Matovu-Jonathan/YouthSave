"""
Non-unit fund cashflow projection.

For each policy year k (0-indexed; Excel's policy year = k+1), combines:
  - unallocated premium:      P * (1 - alloc_rate)
  - B/O spread income:        BO * alloc_rate * P
  - expenses + commissions:   -(ExpenseStrain + CommissionStrain cashflow)
  - non-unit interest:        (above three) * non_unit_fund_growth
  - each strain's per-year cashflow (death/TPD-or-waiver/maturity cost,
    withdrawal charge income) via strain.cashflow(...)
  - AMC income:                mc * fund_after_growth

into the year-by-year PROFIT vector, matching Profit_testing_Plan_A/B's
non-unit fund columns exactly (validated against Excel K16:K25 / X16:X25).
"""

import numpy as np

from engine.unit_fund import get_allocation_rate, project_fund_per_unit_premium


def project_non_unit_fund(decrements, assumptions, plan, premium: float) -> np.ndarray:
    """Returns the PROFIT vector, length term, index k = policy year k+1."""
    n = decrements.term
    fund_per_unit = project_fund_per_unit_premium(assumptions, plan, n)
    fund_closing = fund_per_unit * premium

    profit = np.empty(n)
    opening = 0.0
    for k in range(n):
        duration = k + 1
        alloc_rate = get_allocation_rate(duration, plan)
        alloc_prem = alloc_rate * premium

        unallocated_prem = premium - alloc_prem
        bo_income = assumptions.bid_offer_spread * alloc_prem

        expense = next(s for s in plan.strains if type(s).__name__ == "ExpenseStrain")
        commission = next(s for s in plan.strains if type(s).__name__ == "CommissionStrain")
        expense_outgo = expense.cashflow(k, decrements, assumptions, plan, fund_closing, premium)
        commission_outgo = commission.cashflow(k, decrements, assumptions, plan, fund_closing, premium)

        non_unit_interest = (
            unallocated_prem + bo_income - (expense_outgo + commission_outgo)
        ) * assumptions.non_unit_fund_growth

        # Strain-driven costs/income: withdrawal charge, death/TPD-or-waiver,
        # maturity. Deliberately excludes ExpenseStrain/CommissionStrain
        # (already accounted above) and MaturityStrain is included here
        # since it's a genuine per-year cost line (zero except final year).
        strain_cashflow = 0.0
        for strain in plan.strains:
            name = type(strain).__name__
            if name in ("ExpenseStrain", "CommissionStrain"):
                continue
            strain_cashflow += strain.cashflow(k, decrements, assumptions, plan, fund_closing, premium)

        # AMC income = mc * fund_after_growth. fund_after_growth is the
        # pre-mc fund value: fund_closing[k] = fund_after_growth * (1 - mc),
        # so fund_after_growth = fund_closing[k] / (1 - mc).
        fund_after_growth = fund_closing[k] / (1 - assumptions.annual_management_charge)
        amc_income = assumptions.annual_management_charge * fund_after_growth

        profit[k] = (
            unallocated_prem
            + bo_income
            - (expense_outgo + commission_outgo)
            + non_unit_interest
            + strain_cashflow
            + amc_income
        )

    return profit
