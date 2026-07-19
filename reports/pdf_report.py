"""
"Generate PDF Report" -- builds a client/stakeholder-facing PDF for a
specific configured policy, using the exact same validated engine and
analysis functions as the Streamlit dashboard. No numbers are
recomputed or approximated here; this module only formats output that
engine/ and analysis/ already produced.

Usage:
    from reports.pdf_report import generate_report
    generate_report(policy, plans, base_assumptions, term_rates_df, mort, surr, "output.pdf")
"""

import io
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, Table, TableStyle,
)

from engine.config import assumptions_for_term
from engine.decrements import build_decrement_table, add_waiver_table
from engine.pricing import solve_premium
from engine.profit_testing import price_and_test
from engine.policy import calculate_entry_age, build_policy_plan
from analysis.affordability import compute_affordability, plot_affordability
from analysis.plan_comparison import compare_plans, plot_plan_comparison
from analysis.composition import compute_composition, plot_composition
from analysis.maturity_value import compute_maturity_value
from analysis.tornado_chart import generate_tornado_charts
from analysis.heatmap import plot_margin_heatmaps


def _fig_to_image(fig, width=6.5 * inch):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    img = Image(buf, width=width, height=width * fig.get_size_inches()[1] / fig.get_size_inches()[0])
    return img


def generate_report(policy, plans, base_assumptions, term_rates_df, mort_df, surr_df, output_path: str):
    entry_age = calculate_entry_age(policy.dob, policy.inception_date)
    plan = build_policy_plan(policy, plans[policy.plan_type])
    assumptions = assumptions_for_term(base_assumptions, policy.term, term_rates_df)

    table = build_decrement_table(entry_age, policy.term, policy.gender, mort_df, surr_df)
    if policy.plan_type == "plan_b":
        table = add_waiver_table(table, mort_df, plan.waived_mortality_loading, assumptions.pricing_interest_rate)
    premium = solve_premium(table, assumptions, plan)
    result = price_and_test(table, assumptions, plan, premium, policy.plan_type)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=20, spaceAfter=6)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], spaceBefore=16, spaceAfter=8)
    body = styles["Normal"]
    caption = ParagraphStyle("Caption", parent=styles["Normal"], fontSize=8, textColor=colors.grey, spaceAfter=10)

    story = []

    # --- Header / Policy Summary ---
    story.append(Paragraph("YouthSave Plan — Policy Pricing Report", title_style))
    disclaimer_style = ParagraphStyle(
        "Disclaimer", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#666666"),
        spaceAfter=12, borderPadding=6,
    )
    story.append(Paragraph(
        "<b>Illustrative only.</b> All assumptions, rates, and figures in this report are for "
        "internal modelling and product-development purposes. They are not filed with, "
        "reviewed by, or approved by the Insurance Regulatory Authority of Uganda (IRA), "
        "and do not constitute a policy quotation, offer, or contract. Actual pricing is "
        "subject to regulatory review and may differ from the figures shown here.",
        disclaimer_style,
    ))
    plan_label = "Plan A (TPD Lump Sum)" if policy.plan_type == "plan_a" else "Plan B (TPD Premium Waiver)"
    gender_label = "Male" if policy.gender == "M" else "Female"
    story.append(Paragraph(
        f"Entry Age: {entry_age} &nbsp;|&nbsp; Gender: {gender_label} &nbsp;|&nbsp; "
        f"{plan_label} &nbsp;|&nbsp; Term: {policy.term} years &nbsp;|&nbsp; "
        f"Sum Assured: UGX {policy.sum_assured:,.0f}",
        body,
    ))
    story.append(Spacer(1, 10))

    summary_data = [
        ["Annual Premium", f"UGX {premium:,.0f}"],
        ["Monthly Premium", f"UGX {premium / 12:,.0f}"],
        ["NPV", f"UGX {result.npv:,.0f}"],
        ["PV of Premiums", f"UGX {result.pv_premiums_total:,.0f}"],
        ["Profit Margin", f"{result.profit_margin:.2%}"],
    ]
    t = Table(summary_data, colWidths=[2.5 * inch, 3 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F2F2")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))

    # --- Affordability ---
    story.append(Paragraph("Premium Affordability", h2))
    story.append(Paragraph(
        "Monthly premium as a percentage of monthly income, across a tiered range of "
        "target-market income levels. Bands (≤5% affordable, 5–10% stretched, &gt;10% "
        "inaccessible) are a common microinsurance rule of thumb, not a UBOS or IRA "
        "standard.", body,
    ))
    afford_rows = compute_affordability(premium)
    fig = plot_affordability(afford_rows)
    story.append(_fig_to_image(fig))
    matplotlib.pyplot.close(fig)
    story.append(PageBreak())

    # --- Plan A vs Plan B ---
    story.append(Paragraph("Plan A vs Plan B", h2))
    story.append(Paragraph(
        "Impact of the TPD premium-waiver feature (Plan B) on premium and profit margin, "
        "at this policy's entry age, term, gender, and sum assured.", body,
    ))
    comparison = compare_plans(entry_age, policy.term, policy.gender, policy.sum_assured, plans, base_assumptions, term_rates_df, mort_df, surr_df)
    fig = plot_plan_comparison(comparison)
    story.append(_fig_to_image(fig))
    matplotlib.pyplot.close(fig)
    story.append(Spacer(1, 10))

    # --- Premium Composition ---
    story.append(Paragraph("Premium Composition", h2))
    story.append(Paragraph(
        "Where each shilling of premium (in expected-present-value terms) is allocated, "
        "for this policy's plan.", body,
    ))
    comp_rows = compute_composition(table, assumptions, plan, premium)
    fig = plot_composition(comp_rows, plan_label)
    story.append(_fig_to_image(fig, width=6.5 * inch))
    matplotlib.pyplot.close(fig)
    story.append(PageBreak())

    # --- Maturity Value ---
    story.append(Paragraph("Maturity Value vs. Premiums Paid", h2))
    mv = compute_maturity_value(table, assumptions, plan, premium)
    mv_data = [
        ["Total Premiums Paid (over term)", f"UGX {mv.total_premiums_paid:,.0f}"],
        ["Maturity Value (if policy completes term)", f"UGX {mv.maturity_value_if_completed:,.0f}"],
        ["  -> Ratio", f"{mv.ratio_if_completed:.2f}x"],
        ["Maturity Value (survival-probability-weighted expectation)", f"UGX {mv.maturity_value_expected:,.0f}"],
        ["  -> Ratio", f"{mv.ratio_expected:.2f}x"],
    ]
    t2 = Table(mv_data, colWidths=[4 * inch, 2 * inch])
    t2.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t2)
    story.append(Paragraph(
        "The 'if completed' figure is the illustration value assuming the policy runs to "
        "term without lapse or claim. The 'expectation' figure weights this by the "
        "probability of actually surviving to maturity, and is the more actuarially "
        "honest figure since not every policy reaches maturity.", caption,
    ))
    story.append(Spacer(1, 10))

    # --- Sensitivity / Tornado (this policy's own gender) ---
    story.append(Paragraph("Sensitivity Analysis", h2))
    story.append(Paragraph(
        "Impact of each pricing/experience assumption on profit margin (full reprice, "
        "not a fixed-premium re-test), ranked by magnitude of impact.", body,
    ))
    fig_male, fig_female = generate_tornado_charts(entry_age, policy.term, plans, base_assumptions, term_rates_df, mort_df, surr_df)
    fig_shown = fig_male if policy.gender == "M" else fig_female
    fig_other = fig_female if policy.gender == "M" else fig_male
    story.append(_fig_to_image(fig_shown))
    matplotlib.pyplot.close(fig_shown)
    matplotlib.pyplot.close(fig_other)
    story.append(PageBreak())

    # --- Product-level robustness: Profit Margin Heatmap ---
    story.append(Paragraph("Product-Level Robustness: Profit Margin by Age x Term", h2))
    story.append(Paragraph(
        "Profitability across the full supported entry age (20-35) and term (5-15) range, "
        "both plans and genders -- demonstrating this policy's pricing basis holds up "
        "across the target market, not just at this one configuration.", body,
    ))
    fig, _ = plot_margin_heatmaps(plans, base_assumptions, term_rates_df, mort_df, surr_df)
    story.append(_fig_to_image(fig, width=6.8 * inch))
    matplotlib.pyplot.close(fig)

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.drawString(
            0.7 * inch, 0.4 * inch,
            "Illustrative only -- not filed with or approved by the Insurance Regulatory Authority of Uganda (IRA).",
        )
        canvas.drawRightString(letter[0] - 0.7 * inch, 0.4 * inch, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(output_path, pagesize=letter,
                             topMargin=0.6 * inch, bottomMargin=0.7 * inch,
                             leftMargin=0.7 * inch, rightMargin=0.7 * inch)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return output_path
