"""
Batch policy processing: price and profit-test multiple policies from a
CSV, using the exact same validated engine as everything else -- no
separate batch-specific logic, just a loop over run_policy-equivalent
calls per row.

Kept as a standalone module (not just dashboard code) so it's usable
directly from a script or notebook -- e.g. for aggregate statistics work
that doesn't need the Streamlit UI at all.

Expected CSV columns (header row required):
    dob, gender, plan_type, term, sum_assured

    dob         -- YYYY-MM-DD
    gender      -- "M" or "F"
    plan_type   -- "plan_a" or "plan_b"
    term        -- integer, 5-15
    sum_assured -- numeric, UGX

Optional column:
    inception_date -- YYYY-MM-DD, defaults to today if omitted
"""

from datetime import date, datetime

import pandas as pd

from engine.decrements import build_decrement_table, add_waiver_table
from engine.pricing import solve_premium
from engine.profit_testing import price_and_test
from engine.policy import PolicyInput, calculate_entry_age, build_policy_plan

REQUIRED_COLUMNS = {"dob", "gender", "plan_type", "term", "sum_assured"}


class BatchValidationError(Exception):
    pass


def _parse_date(value) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()


def validate_batch_csv(df: pd.DataFrame) -> list[str]:
    """Returns a list of human-readable error strings (empty if valid)."""
    errors = []
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        errors.append(f"Missing required column(s): {', '.join(sorted(missing))}")
        return errors  # can't validate rows without the columns existing

    for i, row in df.iterrows():
        row_num = i + 2  # +1 for 0-index, +1 for header row
        try:
            _parse_date(row["dob"])
        except (ValueError, TypeError):
            errors.append(f"Row {row_num}: invalid dob '{row['dob']}' (expected YYYY-MM-DD)")

        if str(row["gender"]).strip().upper() not in ("M", "F"):
            errors.append(f"Row {row_num}: gender must be 'M' or 'F', got '{row['gender']}'")

        if str(row["plan_type"]).strip().lower() not in ("plan_a", "plan_b"):
            errors.append(f"Row {row_num}: plan_type must be 'plan_a' or 'plan_b', got '{row['plan_type']}'")

        try:
            term = int(row["term"])
            if not (5 <= term <= 15):
                errors.append(f"Row {row_num}: term {term} outside supported range (5-15)")
        except (ValueError, TypeError):
            errors.append(f"Row {row_num}: invalid term '{row['term']}'")

        try:
            sa = float(row["sum_assured"])
            if sa <= 0:
                errors.append(f"Row {row_num}: sum_assured must be positive, got {sa}")
        except (ValueError, TypeError):
            errors.append(f"Row {row_num}: invalid sum_assured '{row['sum_assured']}'")

    return errors


def process_batch(df: pd.DataFrame, plans, base_assumptions, term_rates_df, mort_df, surr_df) -> pd.DataFrame:
    """
    Prices and profit-tests every row. Assumes validate_batch_csv(df) has
    already been called and returned no errors -- this function does not
    re-validate, it will raise on malformed rows.

    Column note: `npv` is the TOTAL net present value of the profit
    signature (sum of the per-year PV-profit values across the whole
    term) -- this is the same figure Excel's own workbook labels "NPV"
    (validated against Profit_testing_Plan_A!E38), and the same
    aggregation level as engine.profit_testing.PolicyResult.npv. It is
    intentionally NOT the same thing as the per-year "PV Profit" series
    shown in the Single Policy tab's discounted-signature chart -- that's
    a year-by-year array, this is its sum. No rename needed; flagging the
    distinction here since it's a natural thing to wonder about.
    """
    from engine.config import assumptions_for_term

    results = []
    for _, row in df.iterrows():
        inception_date = (
            _parse_date(row["inception_date"]) if "inception_date" in df.columns and pd.notna(row.get("inception_date"))
            else date.today()
        )
        policy = PolicyInput(
            dob=_parse_date(row["dob"]),
            gender=str(row["gender"]).strip().upper(),
            plan_type=str(row["plan_type"]).strip().lower(),
            term=int(row["term"]),
            sum_assured=float(row["sum_assured"]),
            inception_date=inception_date,
        )
        entry_age = calculate_entry_age(policy.dob, policy.inception_date)
        plan = build_policy_plan(policy, plans[policy.plan_type])
        assumptions = assumptions_for_term(base_assumptions, policy.term, term_rates_df)

        table = build_decrement_table(entry_age, policy.term, policy.gender, mort_df, surr_df)
        if policy.plan_type == "plan_b":
            table = add_waiver_table(table, mort_df, plan.waived_mortality_loading, assumptions.pricing_interest_rate)

        premium = solve_premium(table, assumptions, plan)
        result = price_and_test(table, assumptions, plan, premium, policy.plan_type)

        results.append({
            "dob": policy.dob, "gender": policy.gender, "plan_type": policy.plan_type,
            "entry_age": entry_age, "term": policy.term, "sum_assured": policy.sum_assured,
            "annual_premium": premium, "monthly_premium": premium / 12,
            "npv": result.npv, "pv_premiums": result.pv_premiums_total,
            "profit_margin": result.profit_margin,
        })

    return pd.DataFrame(results)
