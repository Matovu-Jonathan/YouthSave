"""
Unit fund projection.

    F_t = [(F_{t-1} + AllocRate_t * P * (1 - BO)) * (1 + g)] * (1 - mc)

Note on build order vs. the original README sequencing: this module's
per-unit-premium projection (project_fund_per_unit_premium) is needed by
strains.py/epv.py BEFORE pricing.py can solve for the premium at all,
since SurrenderStrain's EPV coefficient depends on projected fund values.
Because the recursion is homogeneous linear in P (F_0 = 0, and every
forcing term is proportional to P), F_t = P * f_t where f_t depends only
on assumptions/plan config -- so this function computes f_t using P=1,
and the real premium is multiplied in afterwards by whoever needs it
(SurrenderStrain today, unit_fund_at_premium() below for anyone who later
needs the actual fund in currency terms, e.g. non_unit_fund.py).
"""

import numpy as np


def get_allocation_rate(duration: int, plan) -> float:
    """Allocation rate for policy year `duration` (1-indexed): early years vs year 4+."""
    if duration <= 3:
        return plan.allocation_rate_early
    return plan.allocation_rate_later


def project_fund_per_unit_premium(assumptions, plan, term: int) -> np.ndarray:
    """
    Project the closing unit fund at the end of each policy year, per unit
    of annual premium (i.e. assuming P=1). Returned array has length
    `term`; index k holds the closing fund at the end of policy year k+1
    (matching Excel's Profit_testing H column, e.g. index 0 == H3).
    """
    closing = np.empty(term)
    opening = 0.0
    for k in range(term):
        duration = k + 1
        alloc_rate = get_allocation_rate(duration, plan)
        alloc_prem = alloc_rate * 1.0  # per unit premium
        net_of_bo = alloc_prem * (1 - assumptions.bid_offer_spread)
        fund_after_alloc = opening + net_of_bo
        fund_after_growth = fund_after_alloc * (1 + assumptions.unit_fund_growth)
        closing[k] = fund_after_growth * (1 - assumptions.annual_management_charge)
        opening = closing[k]
    return closing


def unit_fund_at_premium(fund_per_unit_premium: np.ndarray, premium: float) -> np.ndarray:
    """Scale a per-unit-premium fund projection by the actual solved premium."""
    return fund_per_unit_premium * premium
