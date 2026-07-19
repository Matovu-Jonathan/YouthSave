"""
Loads config/assumptions.yaml and config/plan_specs.yaml into typed
dataclasses. Kept separate from decrements.py/strains.py so the YAML
schema can change without touching calculation logic.

TERM-DEPENDENT RATES: unit_fund_growth, risk_discount_rate, and
non_unit_fund_growth are NOT term-invariant -- they're derived from
Bank of Uganda T-bill rates that differ by policy term band (5-9,
10-14, 15). They live in data/term_rates.csv, not assumptions.yaml,
and load_assumptions() deliberately leaves them as None on the base
Assumptions object -- there is no single "the" unit fund growth rate
independent of term. Every call site that prices or profit-tests a
SPECIFIC term must call assumptions_for_term() to get a fully-populated
Assumptions object before using it. Using base_assumptions directly for
pricing/profit-testing (skipping assumptions_for_term) will raise
immediately (None used in arithmetic) rather than silently pricing with
a wrong or missing rate.
"""

from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd
import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass
class Assumptions:
    pricing_interest_rate: float
    bid_offer_spread: float
    inflation_rate: float
    annual_management_charge: float
    withdrawal_charge: float
    allocation_rate_early: float
    allocation_rate_later: float
    # Term-dependent -- None until assumptions_for_term() populates them.
    unit_fund_growth: float = None
    non_unit_fund_growth: float = None
    risk_discount_rate: float = None

    @property
    def discount_factor(self) -> float:
        """v = 1 / (1 + i), pricing interest rate. Term-invariant, safe to use directly."""
        return 1 / (1 + self.pricing_interest_rate)


@dataclass
class PlanSpec:
    name: str
    sum_assured: float
    tpd_benefit_pct_of_sa: float
    initial_commission_rate: float
    renewal_commission_rate: float
    initial_expense_rate: float
    renewal_expense_rate: float
    claim_expense_rate: float
    strains: list
    waived_mortality_loading: float = None

    # Allocation rates live on Assumptions in the YAML (shared economic
    # basis) but plan.allocation_rate_early/_later are read by unit_fund.py
    # -- populated from Assumptions at load time, see load_plan_specs().
    allocation_rate_early: float = None
    allocation_rate_later: float = None


def load_assumptions(path: Path = CONFIG_DIR / "assumptions.yaml") -> Assumptions:
    """
    Returns an Assumptions object with unit_fund_growth, risk_discount_rate,
    and non_unit_fund_growth left as None -- call assumptions_for_term()
    with the policy's actual term before pricing or profit-testing.
    """
    with open(path) as f:
        raw = yaml.safe_load(f)
    return Assumptions(**raw)


def load_term_rates(path: Path = DATA_DIR / "term_rates.csv") -> pd.DataFrame:
    """Term-indexed table: unit_fund_growth, risk_discount_rate, non_unit_fund_growth."""
    df = pd.read_csv(path)
    return df.set_index("term").sort_index()


def assumptions_for_term(base_assumptions: Assumptions, term: int, term_rates_df: pd.DataFrame) -> Assumptions:
    """
    Returns a NEW Assumptions object with the term-dependent rates
    populated from term_rates_df for the given term. base_assumptions
    is never mutated. Raises a clear KeyError if the term isn't in the
    table (e.g. outside the supported 5-15 range), rather than silently
    falling back to a default.
    """
    if term not in term_rates_df.index:
        raise KeyError(
            f"No term-rate row for term={term}. Supported terms: "
            f"{sorted(term_rates_df.index.tolist())}."
        )
    row = term_rates_df.loc[term]
    return replace(
        base_assumptions,
        unit_fund_growth=float(row["unit_fund_growth"]),
        risk_discount_rate=float(row["risk_discount_rate"]),
        non_unit_fund_growth=float(row["non_unit_fund_growth"]),
    )


def load_plan_specs(path: Path = CONFIG_DIR / "plan_specs.yaml", assumptions: Assumptions = None):
    from engine.strains import (
        DeathStrain, TPDStrain, SurrenderStrain, ExpenseStrain,
        CommissionStrain, MaturityStrain, WaiverStrain,
    )
    strain_registry = {
        "death": DeathStrain,
        "tpd": TPDStrain,
        "surrender": SurrenderStrain,
        "expense": ExpenseStrain,
        "commission": CommissionStrain,
        "maturity": MaturityStrain,
        "waiver": WaiverStrain,
    }

    with open(path) as f:
        raw = yaml.safe_load(f)
    plans = {}
    for key, spec in raw.items():
        strain_names = spec.pop("strains")
        plan = PlanSpec(strains=[], **spec)
        plan.strains = [strain_registry[name]() for name in strain_names]
        if assumptions is not None:
            plan.allocation_rate_early = assumptions.allocation_rate_early
            plan.allocation_rate_later = assumptions.allocation_rate_later
        plans[key] = plan
    return plans
