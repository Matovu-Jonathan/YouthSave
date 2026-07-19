"""
Streamlit dashboard: policy inputs -> pricing/profit-testing results ->
tornado sensitivity charts, all driven by the validated engine.

Nothing in this file re-implements or approximates the engine -- every
number shown is produced by the exact same functions validated against
Excel in validation/excel_comparison.py. This file is presentation only.

STATE MANAGEMENT NOTE: st.button() only returns True for the single
script rerun immediately following that specific click -- gating results
behind `if not run_clicked: return` wipes the page on any OTHER button
click. Fixed via st.session_state -- see render_single_policy_tab.

STYLING NOTE: text I generate myself (captions, descriptions) is styled
via the ys_caption()/ys_meta() helpers below, which emit plain HTML with
an explicit class -- NOT via reliance on Streamlit's internal
data-testid attributes. Those are undocumented and can differ between
Streamlit versions/installs, which is almost certainly why some caption
text was still showing as low-contrast grey on a previous round of
feedback despite matching CSS selectors in this exact sandbox -- if the
selector doesn't match on the user's installed version, the override
silently never applies. Controlling markup directly removes that risk
for anything critical to readability.

Run:
    streamlit run dashboard/streamlit_app.py
"""

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import altair as alt
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.config import load_assumptions, load_plan_specs, load_term_rates, assumptions_for_term
from engine.decrements import (
    load_mortality_disability, load_surrender, build_decrement_table, add_waiver_table,
)
from engine.pricing import solve_premium
from engine.profit_testing import price_and_test
from engine.policy import PolicyInput, calculate_entry_age, build_policy_plan
from analysis.tornado_chart import generate_tornado_charts
from analysis.affordability import compute_affordability, plot_affordability
from analysis.plan_comparison import compare_plans, plot_plan_comparison
from analysis.composition import compute_composition, plot_composition
from analysis.maturity_value import compute_maturity_value
from analysis.heatmap import plot_margin_heatmaps
from analysis.batch import validate_batch_csv, process_batch
from reports.pdf_report import generate_report

st.set_page_config(page_title="YouthSave", layout="wide", page_icon="💰")

CUSTOM_CSS = """
<style>
:root {
    --ys-text: #0B1120;             /* near-black, body text */
    --ys-text-secondary: #1F2937;   /* dark grey for descriptions -- darkened further per feedback */
    --ys-text-muted: #6B7280;       /* lighter grey, WCAG-AA safe, footnotes ONLY */
    --ys-accent: #0F766E;
    --ys-accent-faint: rgba(15, 118, 110, 0.10);
    --ys-subtle-grey: #E2E5EA;      /* the slider-rail grey -- reused deliberately elsewhere */
    --ys-divider: #B8BFC9;          /* darkened per feedback -- was too faint */
}

/* ---- Base font: floor matches the subtitle scale, per feedback ---- */
html, body, [class*="css"] { font-size: 19px; }

p, li, .stMarkdown, .stMarkdown p {
    font-size: 1rem !important;
    line-height: 1.65;
    color: var(--ys-text) !important;
}
.ys-caption, p.ys-caption, div .ys-caption, [data-testid="stMarkdownContainer"] p.ys-caption {
    font-size: 0.97rem !important;
    color: #1F2937 !important;
    line-height: 1.6 !important;
    margin: 0.2rem 0 0.6rem 0 !important;
}
.ys-meta, p.ys-meta, [data-testid="stMarkdownContainer"] p.ys-meta {
    color: #6B7280 !important;
    font-size: 0.9rem !important;
}

/* ---- Clear hierarchy: each level visibly larger than the text under it ---- */
h1 { font-size: 2.3rem !important; color: var(--ys-text) !important; font-weight: 800 !important; }
h2, [data-testid="stHeader"] { font-size: 1.8rem !important; margin-top: 1.9rem !important; color: var(--ys-text) !important; font-weight: 700 !important; }
h3, h4 { font-size: 1.35rem !important; color: var(--ys-text) !important; font-weight: 700 !important; }

/* ---- Hero header ---- */
.ys-hero { text-align: center; padding: 1.8rem 0 1.4rem 0; margin-bottom: 0.6rem; }
.ys-hero h1 {
    font-size: 3.3rem !important;
    font-weight: 800 !important;
    background: linear-gradient(90deg, #0F766E 0%, #14B8A6 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
    margin-bottom: 0.35rem !important;
    letter-spacing: -0.02em;
}
.ys-hero p {
    font-size: 1.4rem !important;
    color: var(--ys-text-secondary) !important;
    font-weight: 500;
    margin: 0 !important;
}

/* ---- Metric cards: the most important numbers on the page ---- */
[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 14px;
    padding: 1.4rem 1.5rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04);
    transition: box-shadow 0.2s ease, transform 0.2s ease;
}
[data-testid="stMetric"]:hover {
    box-shadow: 0 4px 12px rgba(15, 118, 110, 0.15);
    transform: translateY(-2px);
}
[data-testid="stMetricLabel"] { font-size: 1.05rem !important; font-weight: 600 !important; color: var(--ys-text-secondary) !important; }
[data-testid="stMetricValue"] { font-size: 2.7rem !important; font-weight: 800 !important; color: var(--ys-text) !important; }
[data-testid="stMetricDelta"] { font-size: 1rem !important; }

/* ---- Buttons ----
   MUST: white text on the solid teal primary button (was hard to read).
   Secondary buttons (Run Sensitivity Analysis, Generate Heatmap, etc.)
   get a faint teal fill at rest so they read as clickable before hover,
   not just plain outlined text. */
.stButton > button, .stDownloadButton > button {
    border-radius: 10px !important;
    padding: 0.65rem 1.4rem !important;
    font-size: 1.05rem !important;
    font-weight: 600 !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
    transition: all 0.2s ease-in-out;
    border: none !important;
}
[data-testid="stBaseButton-primary"] { color: #FFFFFF !important; }
[data-testid="stBaseButton-primary"] p { color: #FFFFFF !important; }
[data-testid="stBaseButton-secondary"] {
    background: var(--ys-accent-faint) !important;
    border: 1px solid rgba(15, 118, 110, 0.25) !important;
    color: var(--ys-accent) !important;
}
[data-testid="stBaseButton-secondary"] p { color: var(--ys-accent) !important; font-weight: 600 !important; }
.stButton > button:hover, .stDownloadButton > button:hover {
    box-shadow: 0 4px 14px rgba(15, 118, 110, 0.3);
    transform: translateY(-1px);
}
[data-testid="stBaseButton-secondary"]:hover { background: rgba(15, 118, 110, 0.18) !important; }

/* ---- Tabs ---- */
[data-testid="stTabs"] button p { font-size: 1.12rem !important; }
[data-testid="stTabs"] button[aria-selected="true"] { color: var(--ys-accent) !important; font-weight: 700 !important; }
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { background-color: var(--ys-accent) !important; transition: left 0.25s ease; }

/* ---- Dropdowns / selectboxes / inputs ---- */
[data-testid="stSelectbox"] label, [data-testid="stNumberInput"] label,
[data-testid="stDateInput"] label, [data-testid="stSlider"] label {
    font-size: 1.05rem !important; font-weight: 600 !important; color: var(--ys-text) !important;
}
[data-baseweb="select"] * { font-size: 1.05rem !important; color: var(--ys-text) !important; }
[data-testid="stNumberInput"] input, [data-testid="stDateInput"] input { font-size: 1.05rem !important; }
[data-baseweb="select"] { border-color: var(--ys-subtle-grey) !important; }

/* ---- Charts: rounded, bordered; capped height so fullscreen isn't overwhelming ---- */
[data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"] {
    border-radius: 12px; overflow: hidden; padding: 0.4rem 0;
}
[data-testid="stFullScreenFrame"] img { max-height: 82vh !important; width: auto !important; object-fit: contain; }

/* ---- Spacing / dividers -- reuse the slider's subtle grey consistently ---- */
[data-testid="stVerticalBlock"] { gap: 1.15rem; }
.block-container { padding-top: 2rem; padding-bottom: 3rem; }
hr { border-color: var(--ys-divider) !important; opacity: 0.8; margin: 1.9rem 0 !important; }
[data-testid="stExpander"] { border-radius: 10px !important; border-color: var(--ys-subtle-grey) !important; }
[data-testid="stMetric"] { border-color: var(--ys-subtle-grey) !important; }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def ys_caption(text: str):
    """
    Styled replacement for st.caption(). Uses a CSS class (ys-caption),
    not an inline style attribute -- confirmed via rendered-DOM inspection
    that Streamlit's HTML sanitizer strips style="" attributes even under
    unsafe_allow_html=True, so an inline-style approach silently does
    nothing. The class survives; see the .ys-caption rule (with a
    deliberately over-specific selector) in CUSTOM_CSS for the actual fix.
    """
    st.markdown(f'<p class="ys-caption">{text}</p>', unsafe_allow_html=True)


CHART_FONT = 15
CHART_TITLE_FONT = 17


def _bar_chart(values: np.ndarray, y_label: str, title: str, height: int = 300):
    """
    Policy-year-indexed bar chart. Explicit Altair (not st.bar_chart's
    dict shortcut) for font control AND to fix the "view as table"
    toggle showing meaningless internal indices -- see prior fix notes.

    width="container" on .properties() is REQUIRED, not optional: without
    it, Altair defaults to a fixed per-category step width regardless of
    what width= Streamlit's own wrapper is given, which is what caused
    the chart to look squeezed/compressed even after the outer
    st.altair_chart(..., width='stretch') was already set.
    """
    df = pd.DataFrame({"Policy Year": np.arange(1, len(values) + 1), y_label: values})
    chart = (
        alt.Chart(df)
        .mark_bar(color="#0F766E", cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("Policy Year:O", axis=alt.Axis(labelFontSize=CHART_FONT, titleFontSize=CHART_TITLE_FONT,
                                                     labelAngle=0, values=list(range(1, len(values) + 1, max(1, len(values) // 5))))),
            y=alt.Y(f"{y_label}:Q", axis=alt.Axis(labelFontSize=CHART_FONT, titleFontSize=CHART_TITLE_FONT)),
            tooltip=["Policy Year", y_label],
        )
        .properties(width="container", height=height, title=alt.TitleParams(title, fontSize=CHART_TITLE_FONT))
        .configure_view(strokeWidth=0)
    )
    return chart, df


def _line_chart(series: dict, x_label: str, title: str, height: int = 260):
    """Same rationale as _bar_chart -- explicit index, matched fonts, width='container'."""
    n = len(next(iter(series.values())))
    df = pd.DataFrame({x_label: np.arange(1, n + 1), **series})
    long_df = df.melt(x_label, var_name="Series", value_name="Value")
    chart = (
        alt.Chart(long_df)
        .mark_line(point=True, strokeWidth=2.5)
        .encode(
            x=alt.X(f"{x_label}:O", axis=alt.Axis(labelFontSize=CHART_FONT, titleFontSize=CHART_TITLE_FONT,
                                                    labelAngle=0, values=list(range(1, n + 1, max(1, n // 5))))),
            y=alt.Y("Value:Q", axis=alt.Axis(labelFontSize=CHART_FONT, titleFontSize=CHART_TITLE_FONT)),
            color=alt.Color("Series:N", scale=alt.Scale(range=["#0F766E", "#94A3B8"]),
                             legend=alt.Legend(labelFontSize=CHART_FONT, titleFontSize=CHART_TITLE_FONT)),
            tooltip=[x_label, "Series", "Value"],
        )
        .properties(width="container", height=height, title=alt.TitleParams(title, fontSize=CHART_TITLE_FONT))
        .configure_view(strokeWidth=0)
    )
    return chart, df


MIN_ENTRY_AGE, MAX_ENTRY_AGE = 20, 35
MIN_TERM, MAX_TERM = 5, 15
MAX_ATTAINED_AGE = 50


@st.cache_data
def load_config():
    base_assumptions = load_assumptions()
    term_rates = load_term_rates()
    plans = load_plan_specs(assumptions=base_assumptions)
    mort = load_mortality_disability()
    surr = load_surrender()
    return base_assumptions, term_rates, plans, mort, surr


def run_policy(policy: PolicyInput, plans, base_assumptions, term_rates, mort, surr):
    entry_age = calculate_entry_age(policy.dob, policy.inception_date)
    plan = build_policy_plan(policy, plans[policy.plan_type])
    assumptions = assumptions_for_term(base_assumptions, policy.term, term_rates)

    table = build_decrement_table(entry_age, policy.term, policy.gender, mort, surr)
    if policy.plan_type == "plan_b":
        table = add_waiver_table(table, mort, plan.waived_mortality_loading, assumptions.pricing_interest_rate)

    premium = solve_premium(table, assumptions, plan)
    result = price_and_test(table, assumptions, plan, premium, policy.plan_type)
    return entry_age, plan, assumptions, result


def render_single_policy_tab(base_assumptions, term_rates, plans, mort, surr):
    with st.sidebar:
        st.header("Policy Inputs")
        dob = st.date_input(
            "Date of Birth", value=date(2001, 1, 1),
            min_value=date(1950, 1, 1), max_value=date.today(),
        )
        gender = st.selectbox("Gender", ["M", "F"], format_func=lambda g: "Male" if g == "M" else "Female")
        plan_type = st.selectbox(
            "Plan Type", ["plan_a", "plan_b"],
            format_func=lambda p: "Plan A (TPD lump sum)" if p == "plan_a" else "Plan B (TPD premium waiver)",
        )
        term = st.slider("Policy Term (years)", MIN_TERM, MAX_TERM, 10)
        sum_assured = st.number_input(
            "Sum Assured (UGX)", min_value=1_000_000, max_value=100_000_000,
            value=3_000_000, step=500_000,
        )
        inception_date = st.date_input("Inception Date", value=date.today())

        entry_age_preview = calculate_entry_age(dob, inception_date)
        st.markdown(
            f'<p class="ys-meta">Computed entry age: <b>{entry_age_preview}</b></p>',
            unsafe_allow_html=True,
        )

        run_clicked = st.button("Price Policy", type="primary", width='stretch')

    warnings = []
    if not (MIN_ENTRY_AGE <= entry_age_preview <= MAX_ENTRY_AGE):
        warnings.append(
            f"Entry age {entry_age_preview} is outside the supported range "
            f"({MIN_ENTRY_AGE}-{MAX_ENTRY_AGE}) per the product brief."
        )
    if entry_age_preview + term > MAX_ATTAINED_AGE:
        warnings.append(
            f"Entry age {entry_age_preview} + term {term} = attained age "
            f"{entry_age_preview + term}, which exceeds the mortality/disability "
            f"table's coverage (up to {MAX_ATTAINED_AGE}). Extend "
            f"data/mortality_disability.csv before pricing this combination."
        )
    for w in warnings:
        st.warning(w)

    if run_clicked:
        if warnings:
            st.error("Cannot price this policy until the warnings above are resolved.")
        else:
            policy = PolicyInput(
                dob=dob, gender=gender, plan_type=plan_type, term=term,
                sum_assured=sum_assured, inception_date=inception_date,
            )
            with st.spinner("Pricing and profit-testing..."):
                entry_age, plan, assumptions, result = run_policy(policy, plans, base_assumptions, term_rates, mort, surr)
            st.session_state["priced"] = {
                "policy": policy, "entry_age": entry_age, "plan": plan,
                "assumptions": assumptions, "result": result,
            }
            st.session_state.pop("tornado_figs", None)
            st.session_state.pop("heatmap_fig", None)

    if "priced" not in st.session_state:
        st.info("Set the policy inputs in the sidebar and click **Price Policy**.")
        return

    policy = st.session_state["priced"]["policy"]
    entry_age = st.session_state["priced"]["entry_age"]
    plan = st.session_state["priced"]["plan"]
    assumptions = st.session_state["priced"]["assumptions"]  # term-resolved, ready to use directly
    result = st.session_state["priced"]["result"]

    # --- Results ---
    st.subheader("Results")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Annual Premium", f"UGX {result.premium:,.0f}")
    col2.metric("Monthly Premium", f"UGX {result.premium / 12:,.0f}")
    col3.metric("NPV", f"UGX {result.npv:,.0f}")
    col4.metric("Profit Margin", f"{result.profit_margin:.2%}")

    ys_caption(
        f"Plan: {plan.name} | Gender: {'Male' if policy.gender == 'M' else 'Female'} | "
        f"Entry age: {entry_age} | Term: {policy.term} years | Sum Assured: UGX {policy.sum_assured:,.0f}"
    )

    st.markdown("#### Year-by-Year Profit Vector")
    profit_chart, _ = _bar_chart(result.profit_vector, "Non-unit fund profit (UGX)", "Profit by Policy Year")
    st.altair_chart(profit_chart, width='stretch')

    with st.expander("Profit build-up by policy year (present value of profit and premium, side by side)"):
        pv_chart, _ = _line_chart(
            {"PV Profit": result.pv_profit, "PV Premium": result.pv_premium},
            "Policy Year", "Profit Build-Up by Policy Year",
        )
        st.altair_chart(pv_chart, width='stretch')

    # --- Affordability ---
    st.markdown("---")
    st.subheader("Premium Affordability")
    ys_caption(
        "Monthly premium as % of monthly income across a tiered range of target-market "
        "income levels. Bands (≤5% affordable, 5-10% stretched, &gt;10% inaccessible) are a "
        "common microinsurance rule of thumb, not a UBOS or IRA standard."
    )
    afford_rows = compute_affordability(result.premium)
    st.pyplot(plot_affordability(afford_rows))

    # --- Plan A vs Plan B ---
    st.markdown("---")
    st.subheader("Plan A vs Plan B")
    with st.spinner("Comparing plans..."):
        comparison = compare_plans(
            entry_age, policy.term, policy.gender, policy.sum_assured, plans, base_assumptions, term_rates, mort, surr
        )
    st.pyplot(plot_plan_comparison(comparison))

    # --- Premium Composition ---
    st.markdown("---")
    st.subheader("Premium Composition")
    ys_caption("Where each shilling of premium (EPV terms) is allocated, for this policy's plan.")
    comp_table = build_decrement_table(entry_age, policy.term, policy.gender, mort, surr)
    if policy.plan_type == "plan_b":
        comp_table = add_waiver_table(comp_table, mort, plan.waived_mortality_loading, assumptions.pricing_interest_rate)
    comp_rows = compute_composition(comp_table, assumptions, plan, result.premium)
    plan_label = "Plan A" if policy.plan_type == "plan_a" else "Plan B"
    st.pyplot(plot_composition(comp_rows, plan_label))

    # --- Maturity Value ---
    st.markdown("---")
    st.subheader("Maturity Value vs. Premiums Paid")
    mv = compute_maturity_value(comp_table, assumptions, plan, result.premium)
    mcol1, mcol2 = st.columns(2)
    mcol1.metric("If policy completes term", f"UGX {mv.maturity_value_if_completed:,.0f}",
                  f"{mv.ratio_if_completed:.2f}x premiums paid")
    mcol2.metric("Survival-weighted expectation", f"UGX {mv.maturity_value_expected:,.0f}",
                  f"{mv.ratio_expected:.2f}x premiums paid")
    ys_caption(f"Total premiums paid over the term: UGX {mv.total_premiums_paid:,.0f}")

    # --- Sensitivity / Tornado charts ---
    st.markdown("---")
    st.subheader("Sensitivity Analysis")
    ys_caption(
        "Re-solves the premium under each stressed assumption and re-runs profit "
        "testing (full reprice, not a fixed-premium re-test) -- both plans, "
        "both genders, at this policy's entry age and term."
    )
    if st.button("Run Sensitivity Analysis"):
        with st.spinner("Running 14 assumptions x 2 directions x 2 plans x 2 genders..."):
            fig_male, fig_female = generate_tornado_charts(entry_age, policy.term, plans, base_assumptions, term_rates, mort, surr)
        st.session_state["tornado_figs"] = (fig_male, fig_female)

    if "tornado_figs" in st.session_state:
        fig_male, fig_female = st.session_state["tornado_figs"]
        tab_male, tab_female = st.tabs(["Male", "Female"])
        with tab_male:
            st.pyplot(fig_male)
        with tab_female:
            st.pyplot(fig_female)

    # --- Profit Margin Heatmap ---
    st.markdown("---")
    st.subheader("Profit Margin Heatmap (Age x Term)")
    ys_caption(
        "Product-level view across the full supported entry age (20-35) and term (5-15) "
        "range, all plans and genders -- demonstrates robustness beyond this one policy. "
        "Rates now step at the term-8/9-to-10 and 14-to-15 boundaries (Bank of Uganda "
        "T-bill bands), so you'll see visible bands rather than a smooth gradient -- "
        "that's correct, not a rendering artifact."
    )
    if st.button("Generate Heatmap"):
        with st.spinner("Solving 704 policy combinations..."):
            fig_heatmap, _ = plot_margin_heatmaps(plans, base_assumptions, term_rates, mort, surr)
        st.session_state["heatmap_fig"] = fig_heatmap

    if "heatmap_fig" in st.session_state:
        st.pyplot(st.session_state["heatmap_fig"])

    # --- PDF Report ---
    st.markdown("---")
    st.subheader("Downloadable Report")
    ys_caption("Illustrative only -- not filed with or approved by the Insurance Regulatory Authority of Uganda (IRA).")
    if st.button("Generate PDF Report", type="primary"):
        with st.spinner("Building PDF report (includes full heatmap + tornado -- may take a moment)..."):
            output_path = "/tmp/YouthSave_Policy_Report.pdf"
            generate_report(policy, plans, base_assumptions, term_rates, mort, surr, output_path)
            with open(output_path, "rb") as f:
                st.session_state["pdf_bytes"] = f.read()

    if "pdf_bytes" in st.session_state:
        st.download_button(
            "Download PDF Report", data=st.session_state["pdf_bytes"],
            file_name=f"YouthSave_{policy.plan_type}_{policy.gender}_{entry_age}yo_{policy.term}yr.pdf",
            mime="application/pdf",
        )


def render_batch_tab(base_assumptions, term_rates, plans, mort, surr):
    st.subheader("Batch Policy Processing")
    ys_caption(
        "Upload a CSV with columns: dob, gender, plan_type, term, sum_assured "
        "(optional: inception_date). Every row is priced and profit-tested through "
        "the same validated engine as the Single Policy tab."
    )

    with st.expander("CSV format example"):
        st.code(
            "dob,gender,plan_type,term,sum_assured\n"
            "2001-03-12,M,plan_a,10,3000000\n"
            "1998-11-05,F,plan_b,12,4000000\n",
            language="csv",
        )

    uploaded = st.file_uploader("Upload policy CSV", type=["csv"])
    if uploaded is None:
        st.info("Upload a CSV to begin.")
        return

    try:
        df = pd.read_csv(uploaded)
    except Exception as e:
        st.error(f"Could not read CSV: {e}")
        return

    errors = validate_batch_csv(df)
    if errors:
        st.error(f"{len(errors)} validation error(s) found -- fix these and re-upload:")
        for e in errors:
            st.write(f"- {e}")
        return

    st.success(f"{len(df)} polic{'y' if len(df) == 1 else 'ies'} validated.")

    if st.button("Price All Policies", type="primary"):
        with st.spinner(f"Pricing {len(df)} policies..."):
            results = process_batch(df, plans, base_assumptions, term_rates, mort, surr)
        st.session_state["batch_results"] = results

    if "batch_results" in st.session_state:
        results = st.session_state["batch_results"]
        st.subheader("Results")
        ys_caption("npv represents the total present value of profits over the policy term.")
        st.dataframe(results, width='stretch')

        st.markdown("#### Aggregate Statistics")
        acol1, acol2, acol3 = st.columns(3)
        acol1.metric("Mean Annual Premium", f"UGX {results['annual_premium'].mean():,.0f}")
        acol2.metric("Mean Profit Margin", f"{results['profit_margin'].mean():.2%}")
        acol3.metric("Total NPV (portfolio)", f"UGX {results['npv'].sum():,.0f}")

        csv_bytes = results.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download Results CSV", data=csv_bytes,
            file_name="YouthSave_Batch_Results.csv", mime="text/csv",
        )


def main():
    base_assumptions, term_rates, plans, mort, surr = load_config()

    st.markdown(
        """
        <div class="ys-hero">
            <h1>YouthSave</h1>
            <p>Build your savings. Protect your future.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_single, tab_batch = st.tabs(["Single Policy", "Batch Processing"])
    with tab_single:
        render_single_policy_tab(base_assumptions, term_rates, plans, mort, surr)
    with tab_batch:
        render_batch_tab(base_assumptions, term_rates, plans, mort, surr)


if __name__ == "__main__":
    main()
