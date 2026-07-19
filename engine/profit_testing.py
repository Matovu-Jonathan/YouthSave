"""
Discounts the non-unit fund profit vector at RDR to produce NPV, PV of
premiums, and profit margin (NPV / PV premiums).

Matches Excel's discounting section exactly:
    PV_profit_t  = PROFIT_t * survival[k] * (1+RDR)^-(k+1)
    PV_premium_t = P * survival[k] * (1+RDR)^-k
where k is 0-indexed policy year (t = k+1), survival[k] = k(aP)x
(cumulative survival to the START of policy year k+1, i.e. before that
year's decrements) -- NOT the survival array's k+1 entry.
"""

from dataclasses import dataclass

import numpy as np

from engine.non_unit_fund import project_non_unit_fund


@dataclass
class PolicyResult:
    plan: str
    gender: str
    entry_age: int
    term: int
    premium: float
    profit_vector: np.ndarray
    pv_profit: np.ndarray
    pv_premium: np.ndarray
    npv: float
    pv_premiums_total: float
    profit_margin: float


def discount_profit_signature(decrements, assumptions, premium: float, profit_vector: np.ndarray):
    n = decrements.term
    rdr = assumptions.risk_discount_rate

    pv_profit = np.empty(n)
    pv_premium = np.empty(n)
    for k in range(n):
        pv_profit[k] = profit_vector[k] * decrements.survival[k] * (1 + rdr) ** -(k + 1)
        pv_premium[k] = premium * decrements.survival[k] * (1 + rdr) ** -k

    npv = pv_profit.sum()
    pv_premiums_total = pv_premium.sum()
    return pv_profit, pv_premium, npv, pv_premiums_total


def price_and_test(decrements, assumptions, plan, premium: float, plan_label: str) -> PolicyResult:
    """Top-level entry point: given a solved premium, run the full profit test."""
    profit_vector = project_non_unit_fund(decrements, assumptions, plan, premium)
    pv_profit, pv_premium, npv, pv_premiums_total = discount_profit_signature(
        decrements, assumptions, premium, profit_vector
    )
    profit_margin = npv / pv_premiums_total

    return PolicyResult(
        plan=plan_label,
        gender=decrements.gender,
        entry_age=decrements.entry_age,
        term=decrements.term,
        premium=premium,
        profit_vector=profit_vector,
        pv_profit=pv_profit,
        pv_premium=pv_premium,
        npv=npv,
        pv_premiums_total=pv_premiums_total,
        profit_margin=profit_margin,
    )
