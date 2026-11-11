"""Flat-rate expenses and the partial tax base under § 7 (Příloha č. 1 DAP).

For every rate category: income -> expenses (percentage, capped) -> partial
base. Each category is capped separately, as the law sets a maximum amount per
percentage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, Decimal

from .issues import Issue, IssueCode, Severity
from .money import format_czk
from .rules import RateCategory, RuleSet


@dataclass(frozen=True)
class RateLine:
    rate: RateCategory
    activities: tuple[str, ...]  # statement headings mapped to this rate
    income: Decimal
    expenses: Decimal
    capped: bool

    @property
    def partial_base(self) -> Decimal:
        return self.income - self.expenses


@dataclass
class TaxSummary:
    lines: list[RateLine] = field(default_factory=list)
    unmapped: dict[str, Decimal] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)

    @property
    def income(self) -> Decimal:
        return sum((line.income for line in self.lines), Decimal(0)) + sum(self.unmapped.values(), Decimal(0))

    @property
    def expenses(self) -> Decimal:
        return sum((line.expenses for line in self.lines), Decimal(0))

    @property
    def partial_base(self) -> Decimal:
        return self.income - self.expenses


def flat_rate_expenses(income: Decimal, rate: RateCategory, income_cap: Decimal) -> tuple[Decimal, bool]:
    """Return ``(expenses, capped)``.

    Rounded *down* to whole crowns: the return is filed in whole CZK, and if
    a fraction must be dropped, claiming slightly less expense is the safe
    direction (it can only increase the tax by less than one crown).
    Negative income (a year dominated by cancellations) yields zero expenses.
    """
    if income <= 0:
        return Decimal(0), False
    capped = income > income_cap
    base = min(income, income_cap)
    expenses = (base * rate.percent / 100).to_integral_value(rounding=ROUND_FLOOR)
    return min(expenses, rate.max_expenses), capped


def compute(
    activity_totals: dict[str, Decimal],
    rules: RuleSet,
    overrides: dict[str, str] | None = None,
) -> TaxSummary:
    """Group statement activities by rate and compute expenses.

    ``overrides`` maps an activity heading to a rate id chosen manually by the
    user for headings the rules do not recognize. A manual choice wins over
    the rules on purpose - the user has the final say.
    """
    overrides = overrides or {}
    grouped: dict[str, tuple[RateCategory, list[str], Decimal]] = {}
    summary = TaxSummary()

    for category, amount in sorted(activity_totals.items()):
        rate = rules.rate(overrides[category]) if category in overrides else None
        rate = rate or rules.rate_for_activity(category)
        if rate is None:
            summary.unmapped[category] = amount
            summary.issues.append(
                Issue(
                    IssueCode.UNKNOWN_ACTIVITY,
                    Severity.ERROR,
                    None,
                    {"category": category, "amount": format_czk(amount)},
                )
            )
            continue
        _, names, total = grouped.get(rate.id, (rate, [], Decimal(0)))
        grouped[rate.id] = (rate, names + [category], total + amount)

    # Keep the order of the rules file (80, 60, 40, 30) - same as the form.
    order = {r.id: i for i, r in enumerate(rules.rates)}
    for rate_id in sorted(grouped, key=order.__getitem__):
        rate, names, income = grouped[rate_id]
        expenses, capped = flat_rate_expenses(income, rate, rules.income_cap)
        summary.lines.append(RateLine(rate, tuple(names), income, expenses, capped))
    return summary
