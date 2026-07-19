"""
Sensitivity analysis engine.

Mechanism, confirmed numerically against Excel (not assumed): every stress
FULLY REPRICES (re-solves the premium via the equivalence principle under
the stressed input) and then retests. This single code path handles both
kinds of assumption correctly without needing to hand-classify them:
  - Assumptions that feed the pricing EPVs (e.g. pricing interest rate,
    mortality) produce a genuinely different premium under stress.
  - Assumptions that ONLY affect profit_testing's discounting (e.g. RDR,
    which never appears in any EPV formula) naturally reprice back to the
    SAME base premium -- the equivalence-principle equation simply doesn't
    depend on RDR -- so "always reprice" is equivalent to "reprice only
    when it matters" without sensitivity.py needing to know which is which.

Replicates the 14 stresses in Sensitivity_Analysis_Plan_A/B: Risk Discount
Rate, Unit Fund Growth, Non-Unit Fund Growth, Pricing Interest Rate,
Inflation Rate, Withdrawal Charge, Initial Commission, Renewal Commission,
Annual Management Charge, Initial Expenses, Renewal Expenses, Mortality
Rates, Disability Rates, Surrender Rates -- each stressed in both
directions, matching Excel's stress magnitudes and additive/multiplicative
conventions exactly (validated in validation/excel_comparison.py).
"""

from dataclasses import dataclass, replace as dc_replace

from engine.decrements import build_decrement_table, add_waiver_table
from engine.pricing import solve_premium
from engine.profit_testing import price_and_test


@dataclass
class StressSpec:
    label: str
    target: str      # "assumption" | "plan" | "mortality" | "disability" | "surrender"
    field: str        # attribute name for assumption/plan targets (unused for decrement targets)
    kind: str          # "additive_pp" | "multiplicative"
    magnitude: float


STRESS_DEFINITIONS = [
    StressSpec("Risk Discount Rate", "assumption", "risk_discount_rate", "additive_pp", 0.02),
    StressSpec("Unit Fund Growth", "assumption", "unit_fund_growth", "additive_pp", 0.02),
    StressSpec("Non-Unit Fund Growth", "assumption", "non_unit_fund_growth", "additive_pp", 0.02),
    StressSpec("Pricing Interest Rate", "assumption", "pricing_interest_rate", "additive_pp", 0.02),
    StressSpec("Inflation Rate", "assumption", "inflation_rate", "additive_pp", 0.02),
    StressSpec("Withdrawal Charge", "assumption", "withdrawal_charge", "additive_pp", 0.02),
    StressSpec("Initial Commission", "plan", "initial_commission_rate", "additive_pp", 0.02),
    StressSpec("Renewal Commission", "plan", "renewal_commission_rate", "multiplicative", 0.10),
    StressSpec("Annual Management Charge", "assumption", "annual_management_charge", "multiplicative", 0.10),
    StressSpec("Initial Expenses", "plan", "initial_expense_rate", "multiplicative", 0.10),
    StressSpec("Renewal Expenses", "plan", "renewal_expense_rate", "multiplicative", 0.10),
    StressSpec("Mortality Rates", "mortality", "qx_d", "multiplicative", 0.10),
    StressSpec("Disability Rates", "disability", "qx_di", "multiplicative", 0.10),
    StressSpec("Surrender Rates", "surrender", "qx_w", "multiplicative", 0.20),
]


def _apply_stress(spec: StressSpec, direction: int, assumptions, plan, mort_df, surr_df):
    """
    direction: +1 or -1. Returns a NEW (assumptions, plan, mort_df, surr_df)
    tuple with exactly one of the four stressed -- originals are untouched
    (dataclasses.replace / DataFrame.copy, no in-place mutation).
    """
    if spec.kind == "additive_pp":
        delta = direction * spec.magnitude
    else:  # multiplicative
        delta = None  # computed per-target below

    if spec.target == "assumption":
        if spec.kind == "additive_pp":
            new_value = getattr(assumptions, spec.field) + delta
        else:
            new_value = getattr(assumptions, spec.field) * (1 + direction * spec.magnitude)
        return dc_replace(assumptions, **{spec.field: new_value}), plan, mort_df, surr_df

    if spec.target == "plan":
        if spec.kind == "additive_pp":
            new_value = getattr(plan, spec.field) + delta
        else:
            new_value = getattr(plan, spec.field) * (1 + direction * spec.magnitude)
        return assumptions, dc_replace(plan, **{spec.field: new_value}), mort_df, surr_df

    if spec.target in ("mortality", "disability"):
        col = "qx_d" if spec.target == "mortality" else "qx_di"
        stressed_mort = mort_df.copy()
        stressed_mort[col] = stressed_mort[col] * (1 + direction * spec.magnitude)
        return assumptions, plan, stressed_mort, surr_df

    if spec.target == "surrender":
        stressed_surr = surr_df.copy()
        stressed_surr["qx_w"] = stressed_surr["qx_w"] * (1 + direction * spec.magnitude)
        return assumptions, plan, mort_df, stressed_surr

    raise ValueError(f"Unknown stress target: {spec.target}")


def _reprice_and_test(entry_age, term, gender, plan_key, assumptions, plan, mort_df, surr_df):
    table = build_decrement_table(entry_age, term, gender, mort_df, surr_df)
    if plan_key == "plan_b":
        table = add_waiver_table(table, mort_df, plan.waived_mortality_loading, assumptions.pricing_interest_rate)
    premium = solve_premium(table, assumptions, plan)
    return price_and_test(table, assumptions, plan, premium, plan_key)


def run_sensitivity(entry_age, term, gender, plan_key, plan, assumptions, mort_df, surr_df):
    """
    Returns a list of dicts, one per (stress, direction), each with the
    stressed profit margin and its delta from base -- mirrors the layout
    of Sensitivity_Analysis_Plan_A/B (Assumption, Stress, PM, Delta PM).

    IMPORTANT: `assumptions` must already have term-dependent rates
    resolved for THIS `term` (via engine.config.assumptions_for_term) --
    this function stresses whatever unit_fund_growth/risk_discount_rate/
    non_unit_fund_growth values it's given as the base, it does not look
    them up itself. Passing an un-resolved base Assumptions object will
    fail immediately (None in arithmetic), by design -- see config.py.
    """
    base_result = _reprice_and_test(entry_age, term, gender, plan_key, assumptions, plan, mort_df, surr_df)
    base_margin = base_result.profit_margin

    rows = []
    for spec in STRESS_DEFINITIONS:
        for direction, direction_label in [(+1, "+"), (-1, "-")]:
            s_assumptions, s_plan, s_mort, s_surr = _apply_stress(
                spec, direction, assumptions, plan, mort_df, surr_df
            )
            result = _reprice_and_test(entry_age, term, gender, plan_key, s_assumptions, s_plan, s_mort, s_surr)
            rows.append({
                "assumption": spec.label,
                "direction": direction_label,
                "stressed_margin": result.profit_margin,
                "delta_margin": result.profit_margin - base_margin,
            })
    return base_margin, rows
