"""
Premium composition breakdown: where each shilling of premium goes.

This is a direct reuse of the strain EPV decomposition already computed
during pricing -- NOT a new formula. Because the premium was solved via
the equivalence principle (EPV premiums = sum of strain EPVs), summing
each strain's EPV-in-currency-terms and dividing by total premium EPV
gives a decomposition that sums to exactly 100% by construction. No new
actuarial assumptions here, just a different view of numbers the engine
already produces.
"""

from dataclasses import dataclass

import matplotlib.pyplot as plt

from engine.epv import premium_annuity_epv

from analysis.chart_style import apply_dashboard_style
apply_dashboard_style()

STRAIN_LABELS = {
    "DeathStrain": "Death Benefit",
    "TPDStrain": "TPD Benefit",
    "WaiverStrain": "TPD Premium Waiver",
    "SurrenderStrain": "Surrender Benefit",
    "MaturityStrain": "Maturity Benefit",
    "ExpenseStrain": "Expenses",
    "CommissionStrain": "Commission",
}

STRAIN_COLORS = {
    "Death Benefit": "#4472C4",
    "TPD Benefit": "#ED7D31",
    "TPD Premium Waiver": "#ED7D31",
    "Surrender Benefit": "#A5A5A5",
    "Maturity Benefit": "#70AD47",
    "Expenses": "#FFC000",
    "Commission": "#5B9BD5",
}


@dataclass
class CompositionRow:
    label: str
    value: float
    pct: float


def compute_composition(decrements, assumptions, plan, premium: float) -> list[CompositionRow]:
    a_prem = premium_annuity_epv(decrements, assumptions)
    total_premium_epv = a_prem * premium

    rows = []
    for strain in plan.strains:
        epv = strain.epv(decrements, assumptions, plan)
        value = epv.fixed + epv.coeff * premium
        label = STRAIN_LABELS.get(type(strain).__name__, type(strain).__name__)
        rows.append(CompositionRow(label, value, value / total_premium_epv))

    return rows


def plot_composition(rows: list[CompositionRow], plan_label: str):
    fig, ax = plt.subplots(figsize=(7, 4.5))

    labels = [r.label for r in rows]
    pcts = [r.pct * 100 for r in rows]
    colors = [STRAIN_COLORS.get(l, "#999999") for l in labels]

    left = 0
    for label, pct, color in zip(labels, pcts, colors):
        ax.barh(0, pct, left=left, color=color, edgecolor="white", label=label)
        if pct > 3:  # only label segments wide enough to read
            ax.text(left + pct / 2, 0, f"{pct:.1f}%", ha="center", va="center", fontsize=8, color="white")
        left += pct

    ax.set_yticks([])
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of Premium EPV")
    ax.set_title(f"Premium Composition -- {plan_label}")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.25), ncol=3, frameon=False, fontsize=8)
    fig.tight_layout()
    return fig
