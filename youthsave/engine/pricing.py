"""
Closed-form equivalence-principle premium solver.

Replaces Excel's Goal Seek: since every EPV component is either fixed or
linear in premium P (see strains.py / epv.py), the equivalence-principle
equation reduces to a single algebraic solve:

    P = Fixed_total / (A_prem - Coeff_total)

Validated to match Excel's Goal Seek output to floating-point precision
(see validation/excel_comparison.py).
"""

from engine.decrements import DecrementTable
from engine.epv import aggregate_epv


def solve_premium(decrements: DecrementTable, assumptions, plan) -> float:
    totals = aggregate_epv(decrements, assumptions, plan)
    return totals.fixed_total / (totals.a_prem - totals.coeff_total)
