"""
Shared matplotlib styling applied to every chart-producing analysis
module (affordability, plan_comparison, composition, heatmap,
tornado_chart), so chart typography is consistent with the dashboard's
own font scale rather than matplotlib's small defaults -- this is what
made charts look "alien" next to the rest of the UI. Imported and
applied once at module load in each analysis file.
"""

import matplotlib.pyplot as plt

DASHBOARD_TEXT_COLOR = "#1F2937"    # near-black, matches dashboard body text
DASHBOARD_MUTED_COLOR = "#6B7280"   # WCAG-AA-safe mid grey, footnotes only


def apply_dashboard_style():
    plt.rcParams.update({
        "font.size": 13,
        "axes.titlesize": 14,
        "axes.titleweight": "bold",
        "axes.labelsize": 12,
        "xtick.labelsize": 11,
        "ytick.labelsize": 11,
        "legend.fontsize": 11,
        "figure.titlesize": 15,
        "text.color": DASHBOARD_TEXT_COLOR,
        "axes.labelcolor": DASHBOARD_TEXT_COLOR,
        "xtick.color": DASHBOARD_TEXT_COLOR,
        "ytick.color": DASHBOARD_TEXT_COLOR,
        "axes.edgecolor": "#D1D5DB",
    })
