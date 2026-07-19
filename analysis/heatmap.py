"""
Profit margin heatmap: Age x Term profitability matrix, small multiples
across Plan A/B x Male/Female (4 panels), since these are the four
genuinely distinct pricing bases in the model.

Grid deliberately spans the full supported range (entry age 20-35,
term 5-15) -- at the boundary (age 35 + term 15 = attained age 50),
this exactly matches mortality_disability.csv's upper bound, so no
cell in the grid falls outside the loaded decrement tables.
"""

import numpy as np
import matplotlib.pyplot as plt

from engine.decrements import build_decrement_table, add_waiver_table
from engine.pricing import solve_premium
from engine.profit_testing import price_and_test

from analysis.chart_style import apply_dashboard_style
apply_dashboard_style()

AGE_RANGE = range(20, 36)   # 20-35 inclusive
TERM_RANGE = range(5, 16)   # 5-15 inclusive


def compute_margin_grid(plan_key, gender, plans, base_assumptions, term_rates_df, mort_df, surr_df,
                         age_range=AGE_RANGE, term_range=TERM_RANGE):
    """Returns a 2D array [age_idx, term_idx] of profit margins."""
    from engine.config import assumptions_for_term

    plan = plans[plan_key]
    grid = np.full((len(age_range), len(term_range)), np.nan)

    for i, age in enumerate(age_range):
        for j, term in enumerate(term_range):
            # Rates vary by term -- resolved fresh for each column, not once for the whole grid.
            assumptions = assumptions_for_term(base_assumptions, term, term_rates_df)
            table = build_decrement_table(age, term, gender, mort_df, surr_df)
            if plan_key == "plan_b":
                table = add_waiver_table(table, mort_df, plan.waived_mortality_loading, assumptions.pricing_interest_rate)
            premium = solve_premium(table, assumptions, plan)
            result = price_and_test(table, assumptions, plan, premium, plan_key)
            grid[i, j] = result.profit_margin

    return grid


def plot_margin_heatmaps(plans, base_assumptions, term_rates_df, mort_df, surr_df,
                          age_range=AGE_RANGE, term_range=TERM_RANGE):
    """4-panel small-multiples figure: Plan A/B x Male/Female."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    panels = [("plan_a", "M", "Plan A -- Male"), ("plan_a", "F", "Plan A -- Female"),
              ("plan_b", "M", "Plan B -- Male"), ("plan_b", "F", "Plan B -- Female")]

    grids = {}
    for plan_key, gender, _ in panels:
        grids[(plan_key, gender)] = compute_margin_grid(
            plan_key, gender, plans, base_assumptions, term_rates_df, mort_df, surr_df, age_range, term_range
        )

    vmin = min(np.nanmin(g) for g in grids.values())
    vmax = max(np.nanmax(g) for g in grids.values())

    im = None
    for ax, (plan_key, gender, title) in zip(axes.flat, panels):
        grid = grids[(plan_key, gender)]
        im = ax.imshow(grid, cmap="RdYlGn", vmin=vmin, vmax=vmax, aspect="auto", origin="lower")

        # Sparser ticks -- full label lists get cramped at dashboard-scale fonts.
        term_list = list(term_range)
        age_list = list(age_range)
        term_ticks = list(range(0, len(term_list), 2))
        age_ticks = list(range(0, len(age_list), 3))
        ax.set_xticks(term_ticks)
        ax.set_xticklabels([term_list[i] for i in term_ticks])
        ax.set_yticks(age_ticks)
        ax.set_yticklabels([age_list[i] for i in age_ticks])
        ax.set_xlabel("Term (years)")
        ax.set_ylabel("Entry Age")
        ax.set_title(title)

    fig.colorbar(im, ax=axes, orientation="vertical", fraction=0.03, pad=0.03, label="Profit Margin")
    fig.suptitle("Profit Margin by Entry Age x Term", fontsize=14)
    return fig, grids
