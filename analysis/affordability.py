"""
Premium affordability analysis: monthly premium as % of monthly income,
across a tiered range of target-market income levels.

Methodology note: the tiers (150k/200k/300k/500k UGX/month) and the
5%/10% affordability bands are a common microinsurance rule-of-thumb,
NOT a UBOS or IRA regulatory standard -- labelled as such wherever
displayed. 200k is UBOS's reported median worker income; the others
bracket it deliberately (below and above) so the analysis honestly
shows who the product serves rather than defending a single number.
"""

from dataclasses import dataclass

import matplotlib.pyplot as plt

from analysis.chart_style import apply_dashboard_style
apply_dashboard_style()

INCOME_TIERS = [
    ("Lower (150k)", 150_000),
    ("Median (200k)", 200_000),
    ("Target (300k)", 300_000),
    ("Upper (500k)", 500_000),
]

GREEN_THRESHOLD = 0.05   # <= 5% of income: affordable
AMBER_THRESHOLD = 0.10   # 5-10%: stretched; > 10%: inaccessible


@dataclass
class AffordabilityRow:
    tier_label: str
    monthly_income: float
    monthly_premium: float
    pct_of_income: float
    band: str  # "green" | "amber" | "red"


def compute_affordability(annual_premium: float, tiers=INCOME_TIERS) -> list[AffordabilityRow]:
    monthly_premium = annual_premium / 12
    rows = []
    for label, income in tiers:
        pct = monthly_premium / income
        if pct <= GREEN_THRESHOLD:
            band = "green"
        elif pct <= AMBER_THRESHOLD:
            band = "amber"
        else:
            band = "red"
        rows.append(AffordabilityRow(label, income, monthly_premium, pct, band))
    return rows


_BAND_COLORS = {"green": "#2E7D32", "amber": "#F9A825", "red": "#C62828"}


def plot_affordability(rows: list[AffordabilityRow], ax=None):
    if ax is None:
        fig, ax = plt.subplots(figsize=(7, 4.5))
    else:
        fig = ax.figure

    labels = [r.tier_label for r in rows]
    pcts = [r.pct_of_income * 100 for r in rows]
    colors = [_BAND_COLORS[r.band] for r in rows]

    bars = ax.bar(labels, pcts, color=colors, edgecolor="white")
    for bar, r in zip(bars, rows):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.2,
                 f"{r.pct_of_income:.1%}", ha="center", fontsize=9)

    ax.axhline(GREEN_THRESHOLD * 100, color="gray", linestyle="--", linewidth=0.8)
    ax.axhline(AMBER_THRESHOLD * 100, color="gray", linestyle="--", linewidth=0.8)
    ax.text(len(labels) - 0.4, GREEN_THRESHOLD * 100 + 0.15, "5% (affordable)", fontsize=7, color="gray")
    ax.text(len(labels) - 0.4, AMBER_THRESHOLD * 100 + 0.15, "10% (stretched)", fontsize=7, color="gray")

    ax.set_ylabel("Monthly Premium as % of Monthly Income")
    ax.set_title("Premium Affordability Across Income Tiers")
    ax.set_ylim(0, max(pcts) * 1.25 + 1)
    fig.tight_layout()
    return fig
