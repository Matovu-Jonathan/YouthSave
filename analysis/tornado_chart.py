"""
Tornado chart generation for sensitivity results.

Design (agreed with stakeholder review):
  - Two charts: Male and Female, hued orange/purple respectively --
    the project's established gender color convention.
  - Within a chart, Plan A vs Plan B shown as paired bars in two shades
    of the chart's hue (dark = Plan A, light = Plan B), not two
    different hues -- keeps each chart to one color family for
    non-actuarial stakeholders.
  - X-axis is DELTA profit margin (percentage points from that plan's
    OWN base case), not absolute margin. Plan A and Plan B have
    different base margins (~15.16% vs ~15.10%), so plotting absolute
    margin would put the two plans on different implicit baselines and
    make bar-length comparison misleading. Delta-from-own-base is the
    fair comparison.
  - Row order (which assumption is nearer the top) is IDENTICAL across
    both the Male and Female charts, ranked by the largest swing seen
    in ANY of the four series (Plan A/B x Male/Female). This lets a
    stakeholder flip between the two charts and have "row 3" mean the
    same assumption in both, at the cost of a chart's own two plans not
    necessarily being in strict internal rank order.
"""

from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np

from analysis.sensitivity import run_sensitivity

from analysis.chart_style import apply_dashboard_style
apply_dashboard_style()

MALE_COLOR_DARK = "#D2691E"    # Plan A, male
MALE_COLOR_LIGHT = "#F4B183"    # Plan B, male
FEMALE_COLOR_DARK = "#6A0DAD"     # Plan A, female
FEMALE_COLOR_LIGHT = "#C9A0DC"     # Plan B, female


@dataclass
class TornadoRow:
    assumption: str
    plan_a_delta_pos: float  # percentage points
    plan_a_delta_neg: float
    plan_b_delta_pos: float
    plan_b_delta_neg: float

    @property
    def max_swing(self) -> float:
        """Largest single-direction move, used for ranking."""
        return max(
            abs(self.plan_a_delta_pos), abs(self.plan_a_delta_neg),
            abs(self.plan_b_delta_pos), abs(self.plan_b_delta_neg),
        )


def _rows_to_lookup(rows):
    """sensitivity.run_sensitivity's row list -> {assumption: {'+': delta, '-': delta}}."""
    lookup = {}
    for r in rows:
        lookup.setdefault(r["assumption"], {})[r["direction"]] = r["delta_margin"] * 100  # to pp
    return lookup


def compute_tornado_data(entry_age, term, plans, base_assumptions, term_rates_df, mort_df, surr_df):
    """
    Runs sensitivity for both plans x both genders and merges into
    per-gender TornadoRow lists, sharing one global assumption order.
    Returns (male_rows, female_rows), both already sorted in the shared
    order (largest combined swing first).
    """
    from engine.config import assumptions_for_term
    assumptions = assumptions_for_term(base_assumptions, term, term_rates_df)

    results = {}
    for plan_key in ["plan_a", "plan_b"]:
        for gender in ["M", "F"]:
            _, rows = run_sensitivity(
                entry_age, term, gender, plan_key, plans[plan_key], assumptions, mort_df, surr_df
            )
            results[(plan_key, gender)] = _rows_to_lookup(rows)

    assumption_labels = list(results[("plan_a", "M")].keys())

    all_rows = {}
    for label in assumption_labels:
        pa_m = results[("plan_a", "M")][label]
        pb_m = results[("plan_b", "M")][label]
        pa_f = results[("plan_a", "F")][label]
        pb_f = results[("plan_b", "F")][label]
        all_rows[label] = {
            "M": TornadoRow(label, pa_m["+"], pa_m["-"], pb_m["+"], pb_m["-"]),
            "F": TornadoRow(label, pa_f["+"], pa_f["-"], pb_f["+"], pb_f["-"]),
        }

    # Global order: rank by the larger of the male/female max_swing for each assumption
    ordered_labels = sorted(
        assumption_labels,
        key=lambda lbl: max(all_rows[lbl]["M"].max_swing, all_rows[lbl]["F"].max_swing),
        reverse=True,
    )

    male_rows = [all_rows[lbl]["M"] for lbl in ordered_labels]
    female_rows = [all_rows[lbl]["F"] for lbl in ordered_labels]
    return male_rows, female_rows


def plot_tornado(rows: list[TornadoRow], gender_label: str, color_dark: str, color_light: str, ax=None):
    """
    Draws one tornado chart (Plan A vs Plan B paired bars) onto `ax`
    (creates a new figure/axes if not supplied). Returns the figure.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(9, 0.55 * len(rows) + 1.5))
    else:
        fig = ax.figure

    n = len(rows)
    y = np.arange(n)
    bar_height = 0.35

    labels = [r.assumption for r in rows]
    pa_pos = [r.plan_a_delta_pos for r in rows]
    pa_neg = [r.plan_a_delta_neg for r in rows]
    pb_pos = [r.plan_b_delta_pos for r in rows]
    pb_neg = [r.plan_b_delta_neg for r in rows]

    # Plan A: upper sub-bar; Plan B: lower sub-bar. Each bar spans from
    # its negative-direction delta to its positive-direction delta.
    ax.barh(y + bar_height / 2, [p - n for p, n in zip(pa_pos, pa_neg)], left=pa_neg,
            height=bar_height, color=color_dark, label="Plan A", edgecolor="white")
    ax.barh(y - bar_height / 2, [p - n for p, n in zip(pb_pos, pb_neg)], left=pb_neg,
            height=bar_height, color=color_light, label="Plan B", edgecolor="white")

    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()  # largest impact at the top
    ax.set_xlabel("Change in Profit Margin (percentage points)")
    ax.set_title(f"Sensitivity of Profit Margin -- {gender_label}")
    ax.legend(loc="lower right", frameon=False)
    ax.grid(axis="x", linestyle=":", alpha=0.5)
    fig.tight_layout()
    return fig


def generate_tornado_charts(entry_age, term, plans, base_assumptions, term_rates_df, mort_df, surr_df):
    """Returns (fig_male, fig_female), row order shared between them."""
    male_rows, female_rows = compute_tornado_data(entry_age, term, plans, base_assumptions, term_rates_df, mort_df, surr_df)
    fig_male = plot_tornado(male_rows, "Male", MALE_COLOR_DARK, MALE_COLOR_LIGHT)
    fig_female = plot_tornado(female_rows, "Female", FEMALE_COLOR_DARK, FEMALE_COLOR_LIGHT)
    return fig_male, fig_female
