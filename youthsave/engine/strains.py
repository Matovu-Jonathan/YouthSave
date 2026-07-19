"""
Composable strain modules.

A "strain" is any cash-flow-affecting event a policy can be exposed to:
death, TPD, surrender, maturity, waiver-of-premium, and (in future) any
added rider. Each strain knows how to compute its own EPV contribution
for pricing, expressed as an EPVComponent(fixed, coeff_on_premium) pair
-- see epv.py for why every component in this model decomposes this way.

Plan A's strain list: [DeathStrain(), TPDStrain(), SurrenderStrain(),
                        ExpenseStrain(), CommissionStrain(), MaturityStrain()]
Plan B's strain list:  same list with TPDStrain() replaced by WaiverStrain()
                        (TPD no longer pays a lump sum in Plan B -- it
                        triggers a premium waiver instead).

No plan-level branching (`if plan.has_waiver`) appears anywhere -- which
strains apply is entirely determined by which Strain objects are included
in the plan's strain list (see main.py / config wiring).

Validated against Excel Pricing_Plan_A / Pricing_Plan_B, base case
(entry age 20, term 10, both genders) -- see validation/excel_comparison.py.
"""

from dataclasses import dataclass

import numpy as np

from engine.decrements import DecrementTable
from engine.unit_fund import project_fund_per_unit_premium


@dataclass
class EPVComponent:
    """fixed: currency amount independent of premium. coeff: multiplies premium P."""
    fixed: float = 0.0
    coeff: float = 0.0

    def __add__(self, other: "EPVComponent") -> "EPVComponent":
        return EPVComponent(self.fixed + other.fixed, self.coeff + other.coeff)


class DeathStrain:
    """(Sd + f), EPV'd over the death decrement. Fixed -- independent of premium."""

    def epv(self, decrements: DecrementTable, assumptions, plan) -> EPVComponent:
        v = assumptions.discount_factor
        total = 0.0
        for k in range(decrements.term):
            benefit = plan.sum_assured + plan.claim_expense_rate * plan.sum_assured
            total += benefit * v ** (k + 1) * decrements.survival[k] * decrements.aq_d[k]
        return EPVComponent(fixed=total)

    def cashflow(self, k, decrements, assumptions, plan, fund_closing, premium) -> float:
        """Extra death cost in non-unit fund year k+1: benefit in excess of fund, if any."""
        benefit = plan.sum_assured + plan.claim_expense_rate * plan.sum_assured
        shortfall = benefit - fund_closing[k]
        if shortfall > 0:
            return -shortfall * decrements.aq_d[k]
        return 0.0


class TPDStrain:
    """Plan A only. (Sdi + f), EPV'd over the disability decrement. Fixed."""

    def epv(self, decrements: DecrementTable, assumptions, plan) -> EPVComponent:
        v = assumptions.discount_factor
        total = 0.0
        for k in range(decrements.term):
            benefit = plan.tpd_benefit_pct_of_sa * plan.sum_assured + plan.claim_expense_rate * plan.sum_assured
            total += benefit * v ** (k + 1) * decrements.survival[k] * decrements.aq_di[k]
        return EPVComponent(fixed=total)

    def cashflow(self, k, decrements, assumptions, plan, fund_closing, premium) -> float:
        """Extra TPD (disability) cost in non-unit fund year k+1, Plan A only."""
        benefit = plan.tpd_benefit_pct_of_sa * plan.sum_assured + plan.claim_expense_rate * plan.sum_assured
        shortfall = benefit - fund_closing[k]
        if shortfall > 0:
            return -shortfall * decrements.aq_di[k]
        return 0.0


class MaturityStrain:
    """(Sd + f) paid at the final duration only. Fixed."""

    def epv(self, decrements: DecrementTable, assumptions, plan) -> EPVComponent:
        v = assumptions.discount_factor
        n = decrements.term
        benefit = plan.sum_assured + plan.claim_expense_rate * plan.sum_assured
        total = benefit * v ** n * decrements.survival[n]
        return EPVComponent(fixed=total)

    def cashflow(self, k, decrements, assumptions, plan, fund_closing, premium) -> float:
        """
        Extra maturity cost -- only nonzero in the final policy year
        (k == term-1). Weighted by ap[k] (probability of SURVIVING the
        final year), not aq_d/aq_di -- this cost applies to policyholders
        who make it to maturity, not to those who decrement out.
        """
        n = decrements.term
        if k != n - 1:
            return 0.0
        benefit = plan.sum_assured + plan.claim_expense_rate * plan.sum_assured
        shortfall = benefit - fund_closing[k]
        if shortfall > 0:
            return -shortfall * decrements.ap[k]
        return 0.0


class SurrenderStrain:
    """
    (1 - withdrawal_charge) * projected unit fund, EPV'd over the
    withdrawal decrement, with mid-year discounting (v^(k+0.5)) since
    withdrawal is assumed to occur mid-policy-year. Coefficient on
    premium -- fund is homogeneous linear in P (see unit_fund.py).

    IMPORTANT: the surrender benefit percentage is NOT an independent
    plan parameter -- it is structurally 1 - withdrawal_charge (the
    insurer keeps the withdrawal charge, the client receives the rest).
    Deliberately derived from assumptions.withdrawal_charge here rather
    than stored as a separate PlanSpec field, so the two can never drift
    out of sync (e.g. under a withdrawal-charge sensitivity stress).
    Confirmed against Excel: stressing wc without also moving the
    surrender benefit gives the wrong answer; deriving it this way
    matches Excel to floating-point precision in both directions.
    """

    def epv(self, decrements: DecrementTable, assumptions, plan) -> EPVComponent:
        v = assumptions.discount_factor
        surrender_pct = 1 - assumptions.withdrawal_charge
        fund_per_unit = project_fund_per_unit_premium(assumptions, plan, decrements.term)
        total_coeff = 0.0
        for k in range(decrements.term):
            surrender_value_per_unit = surrender_pct * fund_per_unit[k]
            total_coeff += (
                surrender_value_per_unit
                * v ** (k + 0.5)
                * decrements.survival[k]
                * decrements.aq_w[k]
            )
        return EPVComponent(coeff=total_coeff)

    def cashflow(self, k, decrements, assumptions, plan, fund_closing, premium) -> float:
        """Withdrawal charge income: wc * closing fund * P(surrender in year k+1)."""
        return assumptions.withdrawal_charge * fund_closing[k] * decrements.aq_w[k]


class ExpenseStrain:
    """
    Initial expense (flat rate on premium, year 1 only) + renewal expense
    (inflated rate on premium, years 2+). Coefficient on premium.
    """

    def epv(self, decrements: DecrementTable, assumptions, plan) -> EPVComponent:
        v = assumptions.discount_factor
        total_coeff = plan.initial_expense_rate * v ** 0 * decrements.survival[0]
        for k in range(1, decrements.term):
            rate = plan.renewal_expense_rate * (1 + assumptions.inflation_rate) ** k
            total_coeff += rate * v ** k * decrements.survival[k]
        return EPVComponent(coeff=total_coeff)

    def cashflow(self, k, decrements, assumptions, plan, fund_closing, premium) -> float:
        """Actual expense outgo in non-unit fund year k+1 (currency, not EPV)."""
        if k == 0:
            return plan.initial_expense_rate * premium
        return plan.renewal_expense_rate * (1 + assumptions.inflation_rate) ** k * premium


class CommissionStrain:
    """
    Initial commission (flat rate on premium, year 1 only) + renewal
    commission (flat rate on premium, years 2+, NOT inflated). Coefficient
    on premium.
    """

    def epv(self, decrements: DecrementTable, assumptions, plan) -> EPVComponent:
        v = assumptions.discount_factor
        total_coeff = plan.initial_commission_rate * v ** 0 * decrements.survival[0]
        for k in range(1, decrements.term):
            total_coeff += plan.renewal_commission_rate * v ** k * decrements.survival[k]
        return EPVComponent(coeff=total_coeff)

    def cashflow(self, k, decrements, assumptions, plan, fund_closing, premium) -> float:
        """Actual commission outgo in non-unit fund year k+1 (currency, not EPV)."""
        if k == 0:
            return plan.initial_commission_rate * premium
        return plan.renewal_commission_rate * premium


class WaiverStrain:
    """
    Plan B only. EPV = premium * P(TPD onset in year k+1) * Wt[k], the
    temporary waiver annuity from decrements.py. Wt is undefined (treated
    as 0) in the final policy year -- matches Excel exactly (the last
    row's Wt cell is blank, contributing 0 to the sum). Coefficient on
    premium (the "prem" in Excel's formula IS the premium being solved for).
    """

    def epv(self, decrements: DecrementTable, assumptions, plan) -> EPVComponent:
        v = assumptions.discount_factor
        n = decrements.term
        wt_padded = np.zeros(n)
        wt_padded[: len(decrements.Wt)] = decrements.Wt  # last year stays 0
        total_coeff = 0.0
        for k in range(n):
            total_coeff += (
                v ** (k + 1) * decrements.survival[k] * decrements.aq_di[k] * wt_padded[k]
            )
        return EPVComponent(coeff=total_coeff)

    def cashflow(self, k, decrements, assumptions, plan, fund_closing, premium) -> float:
        """
        Waiver cost in non-unit fund year k+1: -premium * P(TPD in year k+1) * Wt[k].
        Undiscounted (unlike the EPV version) -- this is a per-year cashflow,
        not a present value. Zero in the final policy year (Wt undefined there).
        """
        n = decrements.term
        wt_padded = np.zeros(n)
        wt_padded[: len(decrements.Wt)] = decrements.Wt
        return -premium * decrements.aq_di[k] * wt_padded[k]
