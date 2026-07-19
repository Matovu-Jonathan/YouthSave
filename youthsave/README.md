# YouthSave Plan — Actuarial Pricing Engine

Python replication and generalisation of the YouthSave_Plan.xlsx multi-decrement
unit-linked endowment pricing/profit-testing model (Plans A and B).

## Build order (matches validation dependency chain)
1. `engine/decrements.py`   — independent -> dependent decrements, survival, waiver annuity **[done, validated]**
2. `engine/unit_fund.py`    — per-unit-premium fund projection **[done, validated]** — built ahead of
   schedule vs. the original plan: SurrenderStrain's EPV needs projected fund
   values, and pricing.py needs SurrenderStrain, so the per-unit-premium fund
   projection had to exist before the premium could be solved at all. This
   works because the fund recursion is homogeneous linear in P (F_0=0), so
   fund-per-unit-premium can be computed with P=1 before P is known.
3. `engine/config.py`       — YAML loader for Assumptions/PlanSpec **[done]** (not in the original
   module list — needed once strains.py/pricing.py required typed config objects)
4. `engine/strains.py`      — composable strain modules (death, TPD, surrender, expense,
   commission, maturity, waiver) **[done, validated]**
5. `engine/epv.py`          — aggregate EPV components per plan **[done, validated]**
6. `engine/pricing.py`      — closed-form premium solve **[done, validated — matches Excel's
   Goal Seek to ~1e-10, both plans, both genders]**
7. `engine/non_unit_fund.py`— non-unit cashflow / strain costs **[done, validated — profit
   vector matches Excel to ~4.7e-9]**
8. `engine/profit_testing.py` — NPV, profit margin **[done, validated — NPV, PV premiums,
   profit margin all match Excel]**
9. `engine/policy.py`        — user input layer (DOB, gender, plan type, term, sum assured)
   **[done]** — the only place these five inputs enter the engine; every other module
   already takes entry_age/term/gender/sum_assured as plain arguments, so adding this
   layer required no changes elsewhere.
10. `analysis/sensitivity.py`  — automated stress testing **[done, validated — all 14 stresses,
    28 rows, match Excel to floating-point precision, including a withdrawal-charge/
    surrender-benefit linkage fix (surrender_pct_of_fund is now derived as
    1 - withdrawal_charge in strains.py, not stored as an independent PlanSpec field)]**
11. `analysis/tornado_chart.py` — tornado chart visualisation of sensitivity results
    **[done]** — Male/Female charts (orange/purple), Plan A vs Plan B as paired bars in
    dark/light shade, delta-from-own-base-margin on the x-axis, one consistent
    assumption ordering shared across both charts.
12. `dashboard/streamlit_app.py` — UI, deferred until validation passes
13. `validation/excel_comparison.py` — **[done, 11/11 checks pass]** on-demand validation
    against YouthSave_Plan.xlsx. NOT a runtime dependency of engine/ or dashboard/ --
    only this script imports openpyxl (see requirements-dev.txt). Run it after any
    future change to engine/ that could plausibly affect the numbers:

        python validation/excel_comparison.py /path/to/YouthSave_Plan.xlsx

Each module is validated cell-by-cell against the Excel workbook
(`validation/excel_comparison.py`) before the next module is built.

## Data
- `data/mortality_disability.csv` — age-indexed, by gender: qx_d, qx_di.
  Extracted directly from BASIS!A4:E54. **Covers ages 20-70, not 18-70** —
  the source workbook has no rates below age 20; ages 18-19 need to be
  supplied before the engine can price entrants below 20. Also note
  age 70's qx_di is blank in the source for both genders (terminal-age gap,
  not a transcription error) — confirm before that age is reachable in a run.
- `data/surrender.csv` — duration-indexed (1-20), qx_w. Rates are identical
  for M/F in the source data (withdrawal isn't gender-differentiated) but the
  `gender` column is still populated for both, matching the schema of
  mortality_disability.csv so the loader doesn't need gender-specific
  branching per file.
  Kept separate from mortality/disability deliberately: lapse behaviour is a
  function of policy duration, not attained age, so the two series use
  different keys once entry age is no longer fixed at 20. For a 20-year-old
  entrant, duration == attained_age - 20, which reconciles exactly against
  the original Excel base case during validation.
  Business rule (not baked into the CSV — applied in decrements.py): no
  surrender permitted in policy years 1-3 or the final year of the term.
- `config/assumptions.yaml` — economic/pricing basis (shared).
- `config/plan_specs.yaml` — per-plan sums assured, expense/commission bases, active strains.

## Analysis modules (stakeholder-agreed scope)
1. `analysis/affordability.py` — premium as % of income, 4 tiers (150k/200k/300k/500k UGX/month)
2. `analysis/heatmap.py` — profit margin, Age (20-35) x Term (5-15), 4 panels (Plan A/B x M/F)
3. `analysis/plan_comparison.py` — Plan A vs Plan B premium/margin impact
4. `analysis/tornado_chart.py` — sensitivity ranking, Male/Female, Plan A vs B paired bars
5. `analysis/composition.py` — premium composition breakdown (supplementary, supports Innovation)
6. `analysis/maturity_value.py` — maturity value vs. premiums paid (supplementary, supports Affordability)

`reports/pdf_report.py` — "Generate PDF Report" button in the dashboard, built on
reportlab. Calls the exact same engine/analysis functions as the dashboard -- no
numbers are recomputed or approximated for the PDF specifically.

## Final scope additions (post-launch review)
- Default Sum Assured in the dashboard changed 6M -> 3M UGX (entry-level product
  positioning; 6M repositioned as an aspirational configuration, per affordability
  analysis findings).
- `reports/pdf_report.py` now includes a compliance disclaimer -- prominent notice
  on page 1, footer on every page -- stating figures are illustrative and not filed
  with or approved by the Insurance Regulatory Authority of Uganda (IRA).
- `analysis/batch.py` -- batch CSV processing, standalone module (usable outside
  Streamlit, e.g. directly in a script/notebook for dissertation aggregate-stats
  work). `validate_batch_csv()` checks every row before any pricing runs; errors
  report the exact row number and reason. Wired into the dashboard as a
  "Batch Processing" tab alongside "Single Policy" -- upload CSV, price all,
  view aggregate stats, download results CSV.
- Actuarial commentary in the PDF: explicitly out of scope -- the report stays
  numbers/charts only, narrative lives in the dissertation.
