from decimal import Decimal

from commission_tax_calc.core.issues import IssueCode
from commission_tax_calc.core.rules import RulesRepository
from commission_tax_calc.core.tax import compute, flat_rate_expenses

RULES, _ = RulesRepository(None).get(2026)
NOT_A_TRADE = "Není živností, řídí se zvláštním předpisem"


def test_forty_percent_rounded_down():
    summary = compute({NOT_A_TRADE: Decimal(741)}, RULES)
    (line,) = summary.lines
    assert line.rate.percent == 40
    assert line.expenses == Decimal(296)  # 296.4 -> 296
    assert line.partial_base == Decimal(445)
    assert summary.partial_base == Decimal(445)


def test_cap_applies_per_rate():
    rate = RULES.rate("trades")
    expenses, capped = flat_rate_expenses(Decimal(3_000_000), rate, RULES.income_cap)
    assert expenses == Decimal(1_200_000)
    assert capped


def test_negative_income_has_no_expenses():
    rate = RULES.rate("trades")
    assert flat_rate_expenses(Decimal(-500), rate, RULES.income_cap) == (Decimal(0), False)


def test_categories_with_same_rate_are_merged_and_ordered():
    summary = compute(
        {
            NOT_A_TRADE: Decimal(1000),
            "Jiné podnikání – zvláštním předpisem": Decimal(500),
            "Živnost volná": Decimal(2000),
        },
        RULES,
    )
    assert [line.rate.percent for line in summary.lines] == [60, 40]
    forty = summary.lines[1]
    assert forty.income == Decimal(1500)
    assert len(forty.activities) == 2


def test_unknown_activity_is_reported_and_not_lost():
    summary = compute({"Tajemná činnost": Decimal(1000)}, RULES)
    assert summary.lines == []
    assert summary.unmapped == {"Tajemná činnost": Decimal(1000)}
    assert summary.income == Decimal(1000)  # still part of income
    assert summary.issues[0].code is IssueCode.UNKNOWN_ACTIVITY


def test_override_wins():
    summary = compute({"Tajemná činnost": Decimal(1000)}, RULES, {"Tajemná činnost": "trades"})
    assert summary.lines[0].expenses == Decimal(600)
    assert not summary.unmapped
