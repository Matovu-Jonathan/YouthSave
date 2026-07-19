"""
Plan A vs Plan B comparison: premium and profit margin side-by-side for
a given (entry_age, term, gender, sum_assured) -- shows the cost of the
TPD premium-waiver innovation to both client (premium) and insurer
(profit margin), holding everything else constant.
"""

from dataclasses import dataclass

import matplotlib.pyplot as plt

from engine.decrements import build_decrement_table, add_waiver_table
from engine.pricing import solve_premium
from engine.profit_testing import price_and_test

from analysis.chart_style import apply_dashboard_style
apply_dashboard_style()


@dataclass
class PlanComparison:
    premium_a: float
    premium_b: float
    margin_a: float
    margin_b: float

    @property
    def premium_delta(self) -> float:
        return self.premium_b - self.premium_a

    @property
    def margin_delta_pp(self) -> float:
        return (self.margin_b - self.margin_a) * 100


def compare_plans(entry_age, term, gender, sum_assured, plans, base_assumptions, term_rates_df, mort_df, surr_df) -> PlanComparison:
    from dataclasses import replace
    from engine.config import assumptions_for_term

    assumptions = assumptions_for_term(base_assumptions, term, term_rates_df)

    plan_a = replace(plans["plan_a"], sum_assured=sum_assured)
    plan_b = replace(plans["plan_b"], sum_assured=sum_assured)

    table_a = build_decrement_table(entry_age, term, gender, mort_df, surr_df)
    premium_a = solve_premium(table_a, assumptions, plan_a)
    result_a = price_and_test(table_a, assumptions, plan_a, premium_a, "plan_a")

    table_b = build_decrement_table(entry_age, term, gender, mort_df, surr_df)
    table_b = add_waiver_table(table_b, mort_df, plan_b.waived_mortality_loading, assumptions.pricing_interest_rate)
    premium_b = solve_premium(table_b, assumptions, plan_b)
    result_b = price_and_test(table_b, assumptions, plan_b, premium_b, "plan_b")

    return PlanComparison(premium_a, premium_b, result_a.profit_margin, result_b.profit_margin)


def plot_plan_comparison(comparison: PlanComparison):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))

    premiums = [comparison.premium_a, comparison.premium_b]
    ax1.bar(["Plan A", "Plan B"], premiums, color=["#4472C4", "#ED7D31"])
    ax1.set_ylabel("Annual Premium (UGX)")
    ax1.set_title("Premium")
    ax1.set_ylim(0, max(premiums) * 1.18)  # headroom so value labels never clip at the top
    for i, v in enumerate(premiums):
        ax1.text(i, v, f"{v:,.0f}", ha="center", va="bottom", fontsize=11)

    margins = [comparison.margin_a * 100, comparison.margin_b * 100]
    ax2.bar(["Plan A", "Plan B"], margins, color=["#4472C4", "#ED7D31"])
    ax2.set_ylabel("Profit Margin (%)")
    ax2.set_title("Profit Margin")
    ax2.set_ylim(0, max(margins) * 1.18)
    for i, v in enumerate(margins):
        ax2.text(i, v, f"{v:.2f}%", ha="center", va="bottom", fontsize=11)

    fig.suptitle(
        f"Plan A vs Plan B  --  TPD waiver: {comparison.premium_delta:+,.0f} UGX premium, "
        f"{comparison.margin_delta_pp:+.2f}pp margin"
    )
    fig.tight_layout()
    return fig
