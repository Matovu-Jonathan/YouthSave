"""
Maturity value vs. total premiums paid: "what you get back vs. what you
put in" -- affordability from the client's side, not just the insurer's.

Two figures shown deliberately:
  - "If you complete the term" value: the deterministic unit fund at
    maturity (fund_closing[-1]), which is what a client-facing benefit
    illustration would show -- the value assuming the policy runs to
    term without lapse or claim.
  - "Expected" value: the same fund value weighted by the probability of
    actually surviving to maturity (survival[term]), which is the more
    actuarially honest figure since not every policy reaches maturity.
Both are shown, labelled, rather than picking one -- they answer
different questions and conflating them would be misleading either way.
"""

from dataclasses import dataclass

from engine.unit_fund import project_fund_per_unit_premium


@dataclass
class MaturityValueResult:
    total_premiums_paid: float
    maturity_value_if_completed: float
    maturity_value_expected: float
    ratio_if_completed: float
    ratio_expected: float


def compute_maturity_value(decrements, assumptions, plan, premium: float) -> MaturityValueResult:
    term = decrements.term
    total_premiums_paid = premium * term

    fund_per_unit = project_fund_per_unit_premium(assumptions, plan, term)
    maturity_value_if_completed = fund_per_unit[-1] * premium
    maturity_value_expected = maturity_value_if_completed * decrements.survival[term]

    return MaturityValueResult(
        total_premiums_paid=total_premiums_paid,
        maturity_value_if_completed=maturity_value_if_completed,
        maturity_value_expected=maturity_value_expected,
        ratio_if_completed=maturity_value_if_completed / total_premiums_paid,
        ratio_expected=maturity_value_expected / total_premiums_paid,
    )
