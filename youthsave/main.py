"""
Driver script -- demonstrates the full validated engine (decrements ->
unit_fund -> strains -> epv -> pricing -> non_unit_fund -> profit_testing)
driven entirely by the five user-facing inputs: DOB, gender, plan type,
term, sum assured. No other entry point into the engine assumes a fixed
entry age, term, or sum assured -- every module takes these as arguments.

Run:
    python main.py
"""

from datetime import date

from engine.config import load_assumptions, load_plan_specs, load_term_rates, assumptions_for_term
from engine.decrements import (
    load_mortality_disability,
    load_surrender,
    build_decrement_table,
    add_waiver_table,
)
from engine.pricing import solve_premium
from engine.profit_testing import price_and_test
from engine.policy import PolicyInput, calculate_entry_age, build_policy_plan


def run_policy(policy: PolicyInput, plans, base_assumptions, term_rates, mort, surr):
    entry_age = calculate_entry_age(policy.dob, policy.inception_date)
    plan = build_policy_plan(policy, plans[policy.plan_type])

    # Unit fund growth / RDR / non-unit fund growth vary by term (Bank of
    # Uganda T-bill derived) -- must be resolved per-policy, here, not once globally.
    assumptions = assumptions_for_term(base_assumptions, policy.term, term_rates)

    table = build_decrement_table(entry_age, policy.term, policy.gender, mort, surr)
    if policy.plan_type == "plan_b":
        table = add_waiver_table(
            table, mort, plan.waived_mortality_loading, assumptions.pricing_interest_rate
        )

    premium = solve_premium(table, assumptions, plan)
    result = price_and_test(table, assumptions, plan, premium, policy.plan_type)
    return entry_age, result


def main():
    base_assumptions = load_assumptions()
    term_rates = load_term_rates()
    plans = load_plan_specs(assumptions=base_assumptions)
    mort = load_mortality_disability()
    surr = load_surrender()

    example_policies = [
        PolicyInput(dob=date(2001, 3, 12), gender="M", plan_type="plan_a", term=10, sum_assured=6_000_000),
        PolicyInput(dob=date(1998, 11, 5), gender="F", plan_type="plan_b", term=12, sum_assured=8_000_000),
        PolicyInput(dob=date(2003, 6, 1), gender="M", plan_type="plan_a", term=5, sum_assured=3_000_000),
    ]

    print(f"{'Plan':<8}{'Gender':<8}{'Entry Age':<11}{'Term':<6}{'Premium':>16}{'Profit Margin':>16}")
    print("-" * 65)
    for policy in example_policies:
        entry_age, result = run_policy(policy, plans, base_assumptions, term_rates, mort, surr)
        print(
            f"{policy.plan_type:<8}{policy.gender:<8}{entry_age:<11}{policy.term:<6}"
            f"{result.premium:>16,.2f}{result.profit_margin:>16.4%}"
        )


if __name__ == "__main__":
    main()
