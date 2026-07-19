"""
Decrement table construction.

Responsibilities:
  - Load independent (raw) rates from two separately-indexed sources:
      * data/mortality_disability.csv  -- qx_d, qx_di, indexed by (age, gender)
      * data/surrender.csv             -- qx_w, indexed by (duration, gender)
    Age and duration are NOT assumed equal. A policy's duration-t lapse rate
    is looked up by t (years since inception) regardless of entry age; a
    policy's attained-age mortality/disability rate is looked up by
    entry_age + t. For a 20-year-old entrant, duration == attained_age - 20,
    which is what lets this reconcile exactly against the original Excel
    base-case (entry age 20) during validation.
  - Convert independent -> dependent (aq) rates using the UDD approximation,
    combining the age-indexed and duration-indexed series into a single
    per-policy-year decrement table for a given entry age and term.
  - Build cumulative survival probabilities tP_{entry_age}.
  - Build the waiver-state table: mortality loaded by a configurable factor
    (plan_specs.yaml -> waived_mortality_loading, 1.5x in the base case)
    while TPD-waived, and the temporary annuity-due
    Wt = Nt / (t+1)P_{entry_age} via backward recursion.

Business rule: surrender is not permitted in policy years 1-3 or in the
final policy year of the chosen term (e.g. term=10 -> no surrender in
years 1,2,3,10; term=15 -> no surrender in years 1,2,3,15). This is a
product-term-relative rule, not a fixed-duration one, so it is NOT baked
into surrender.csv (which holds the raw duration-indexed qx_w curve) --
it is applied here, when building the per-policy decrement table for a
specific term, by zeroing qx_w in the excluded years.

This is the lowest-level module -- pricing.py, unit_fund.py, non_unit_fund.py,
and profit_testing.py all consume its outputs and never re-derive decrement
rates themselves.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_mortality_disability(path: Path = DATA_DIR / "mortality_disability.csv") -> pd.DataFrame:
    """Age-indexed independent rates. Columns: age, gender, qx_d, qx_di."""
    df = pd.read_csv(path)
    df = df.set_index(["age", "gender"]).sort_index()
    return df


def load_surrender(path: Path = DATA_DIR / "surrender.csv") -> pd.DataFrame:
    """Duration-indexed independent rates. Columns: duration, gender, qx_w."""
    df = pd.read_csv(path)
    df = df.set_index(["duration", "gender"]).sort_index()
    return df


# --------------------------------------------------------------------------
# UDD independent -> dependent conversion
# --------------------------------------------------------------------------

def udd_dependent_rates(qx_d: float, qx_di: float, qx_w: float) -> tuple[float, float, float]:
    """
    Convert three independent decrement rates to dependent (aq) rates
    under the uniform distribution of decrements (UDD) assumption.

    Standard three-decrement UDD formula (each decrement symmetric in the
    other two):
        (aq)^a = q^a * [1 - 1/2*(q^b + q^c) + 1/3*q^b*q^c]
    """
    aq_d = qx_d * (1 - 0.5 * (qx_di + qx_w) + (1 / 3) * qx_di * qx_w)
    aq_di = qx_di * (1 - 0.5 * (qx_d + qx_w) + (1 / 3) * qx_d * qx_w)
    aq_w = qx_w * (1 - 0.5 * (qx_d + qx_di) + (1 / 3) * qx_d * qx_di)
    return aq_d, aq_di, aq_w


# --------------------------------------------------------------------------
# Surrender lookup with the "no surrender" product rule applied
# --------------------------------------------------------------------------

def get_surrender_rate(duration: int, gender: str, term: int, surrender_df: pd.DataFrame) -> float:
    """
    Raw duration-indexed qx_w, with the product restriction applied:
    zero in policy years 1-3 and in the final year of the term, regardless
    of what the raw published table says for that duration.
    """
    if duration <= 3 or duration == term:
        return 0.0
    return float(surrender_df.loc[(duration, gender), "qx_w"])


# --------------------------------------------------------------------------
# Per-policy decrement table
# --------------------------------------------------------------------------

@dataclass
class DecrementTable:
    entry_age: int
    term: int
    gender: str

    ages: np.ndarray          # attained age at start of each policy year, length term
    durations: np.ndarray     # policy year number 1..term, length term

    qx_d: np.ndarray          # independent rates, length term
    qx_di: np.ndarray
    qx_w: np.ndarray          # already has the no-surrender rule applied

    aq_d: np.ndarray          # UDD-dependent rates, length term
    aq_di: np.ndarray
    aq_w: np.ndarray
    ap: np.ndarray

    survival: np.ndarray      # tP_entry_age, length term+1, survival[0] = 1.0

    # Waiver-state fields (populated only when a waiver-loading factor is supplied)
    aq_d_waived: np.ndarray = None
    waived_survival: np.ndarray = None
    Wt: np.ndarray = None


def build_decrement_table(
    entry_age: int,
    term: int,
    gender: str,
    mortality_df: pd.DataFrame,
    surrender_df: pd.DataFrame,
) -> DecrementTable:
    """
    Build the full independent -> dependent -> survival decrement table
    for one (entry_age, term, gender) policy.
    """
    ages = np.array([entry_age + k for k in range(term)])
    durations = np.array([k + 1 for k in range(term)])

    qx_d = np.empty(term)
    qx_di = np.empty(term)
    qx_w = np.empty(term)

    for k in range(term):
        age = ages[k]
        duration = durations[k]
        row = mortality_df.loc[(age, gender)]
        qx_d[k] = row["qx_d"]
        qx_di[k] = row["qx_di"]
        qx_w[k] = get_surrender_rate(duration, gender, term, surrender_df)

    aq_d = np.empty(term)
    aq_di = np.empty(term)
    aq_w = np.empty(term)
    for k in range(term):
        aq_d[k], aq_di[k], aq_w[k] = udd_dependent_rates(qx_d[k], qx_di[k], qx_w[k])

    ap = 1.0 - (aq_d + aq_di + aq_w)

    survival = np.empty(term + 1)
    survival[0] = 1.0
    for k in range(term):
        survival[k + 1] = survival[k] * ap[k]

    return DecrementTable(
        entry_age=entry_age,
        term=term,
        gender=gender,
        ages=ages,
        durations=durations,
        qx_d=qx_d,
        qx_di=qx_di,
        qx_w=qx_w,
        aq_d=aq_d,
        aq_di=aq_di,
        aq_w=aq_w,
        ap=ap,
        survival=survival,
    )


# --------------------------------------------------------------------------
# Waiver-state table (Plan B only)
# --------------------------------------------------------------------------

def add_waiver_table(
    table: DecrementTable,
    mortality_df: pd.DataFrame,
    waived_mortality_loading: float,
    pricing_interest_rate: float,
) -> DecrementTable:
    """
    Extends a DecrementTable with the waiver-state annuity Wt, used to
    price/reserve for continuing to fund the unit account after TPD
    without further premium (Plan B's WaiverStrain).

    While waived, the life is subject only to loaded mortality (no further
    disability or surrender decrement -- once waived, those don't recur),
    and that loaded mortality also determines the survival probability
    used to convert Nt into an annuity rate -- confirmed against Excel and
    against actuarial logic: a disabled life's own survival experience is
    what should discount its own future benefit, not an able-bodied life's.

    Nt is a backward recursion over the waived-state survival, discounted
    at the pricing interest rate, but only spans policy years 1 to term-1
    (k=0..term-2) -- matching Excel exactly, since there is no need to fund
    a waiver triggered in the final policy year (nothing left to waive).

        Nt[term-2] = waived_survival[term-1]
        Nt[k]      = waived_survival[k+1] + v * Nt[k+1]      for k = term-3 .. 0

        Wt[k] = Nt[k] / waived_survival[k+1]                 for k = 0 .. term-2

    Wt has length term-1, not term: there is no waiver value defined for
    the final policy year, consistent with the last-year exclusion also
    applied to surrender.
    """
    v = 1 / (1 + pricing_interest_rate)
    term = table.term

    # Loaded mortality while waived; re-derive dependent rate with di=w=0
    # since once waived, disability has already occurred and surrender
    # no longer applies -- only (loaded) mortality persists.
    aq_d_waived = np.empty(term)
    for k in range(term):
        row = mortality_df.loc[(table.ages[k], table.gender)]
        qx_d_loaded = min(row["qx_d"] * waived_mortality_loading, 1.0)
        aq_d_waived[k], _, _ = udd_dependent_rates(qx_d_loaded, 0.0, 0.0)

    ap_waived = 1.0 - aq_d_waived
    waived_survival = np.empty(term + 1)
    waived_survival[0] = 1.0
    for k in range(term):
        waived_survival[k + 1] = waived_survival[k] * ap_waived[k]

    # Nt/Wt only span k=0..term-2 (term-1 values) -- no waiver value in the
    # final policy year.
    n_vals = term - 1
    Nt = np.zeros(n_vals)
    Nt[n_vals - 1] = waived_survival[n_vals]          # = waived_survival[term-1]
    for k in range(n_vals - 2, -1, -1):
        Nt[k] = waived_survival[k + 1] + v * Nt[k + 1]

    # Wt = Nt / waived-state survival to k+1 (loaded mortality denominator,
    # confirmed correct and intentional).
    Wt = np.array([Nt[k] / waived_survival[k + 1] for k in range(n_vals)])

    table.aq_d_waived = aq_d_waived
    table.waived_survival = waived_survival
    table.Wt = Wt
    return table
