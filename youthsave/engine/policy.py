"""
Client-facing policy input layer.

This is the ONLY place user-facing inputs (DOB, gender, plan type, term,
sum assured) enter the engine. Everything downstream (decrements.py,
strains.py, pricing.py, non_unit_fund.py, profit_testing.py) already
takes entry_age/term/gender/plan as arguments -- nothing about them is
hardcoded to the base-case illustration (entry age 20, term 10, Sd=6M)
we validated against. That base case now arrives through this layer like
any other policy, not as a special path.

Adding a policy here does NOT require touching any engine module --
that's the point of having built entry_age/term/sum_assured as function
parameters from the start rather than YAML constants.
"""

from dataclasses import dataclass, replace
from datetime import date


@dataclass
class PolicyInput:
    dob: date
    gender: str          # "M" or "F"
    plan_type: str        # "plan_a" or "plan_b" -- matches config/plan_specs.yaml keys
    term: int              # 5-15 per product brief
    sum_assured: float
    inception_date: date = None  # defaults to today if not supplied

    def __post_init__(self):
        if self.inception_date is None:
            self.inception_date = date.today()


def calculate_entry_age(dob: date, inception_date: date) -> int:
    """
    Age last birthday as of inception_date -- the standard actuarial
    convention and the simplest to reconcile against a model where entry
    age was previously just typed in directly. Flagging this as an
    assumption worth confirming: if your business rule is "age nearest
    birthday" instead, this is the one function to change.
    """
    age = inception_date.year - dob.year
    if (inception_date.month, inception_date.day) < (dob.month, dob.day):
        age -= 1
    return age


def build_policy_plan(policy: PolicyInput, plan_spec):
    """
    Returns a copy of the config-loaded PlanSpec with sum_assured
    overridden by the policy's actual input. Rates, strain list, and
    allocation bands stay as the shared plan configuration; sum_assured
    is the one field that is genuinely per-policy, not per-plan-type.
    """
    return replace(plan_spec, sum_assured=policy.sum_assured)
