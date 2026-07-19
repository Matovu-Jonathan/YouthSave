"""
Aggregates EPV components from a plan's active strain list.

Every strain returns an EPVComponent(fixed, coeff_on_premium). Summing
across the strain list, plus the premium annuity coefficient A_prem,
gives pricing.py everything it needs for the closed-form solve:

    P * A_prem = Fixed_total + P * Coeff_total
    P = Fixed_total / (A_prem - Coeff_total)
"""

from dataclasses import dataclass

from engine.decrements import DecrementTable
from engine.strains import EPVComponent


@dataclass
class EPVTotals:
    fixed_total: float
    coeff_total: float
    a_prem: float  # EPV of a unit premium annuity-due


def premium_annuity_epv(decrements: DecrementTable, assumptions) -> float:
    """A_prem = sum_{k=0}^{n-1} v^k * survival[k] -- EPV of a unit premium stream."""
    v = assumptions.discount_factor
    return sum(v ** k * decrements.survival[k] for k in range(decrements.term))


def aggregate_epv(decrements: DecrementTable, assumptions, plan) -> EPVTotals:
    total = EPVComponent()
    for strain in plan.strains:
        total = total + strain.epv(decrements, assumptions, plan)

    a_prem = premium_annuity_epv(decrements, assumptions)

    return EPVTotals(fixed_total=total.fixed, coeff_total=total.coeff, a_prem=a_prem)
