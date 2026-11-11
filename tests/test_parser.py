from datetime import date
from decimal import Decimal

import pytest

from commission_tax_calc.core.parser import ParseError, parse_text
from factory import Spec, make_text


def test_parses_basic_statement():
    st = parse_text(make_text(Spec()))
    assert st.period.start == date(2030, 1, 1)
    assert st.period.end == date(2030, 1, 14)
    assert st.holder == "Testovací Tomáš"
    assert st.summary.total == Decimal(1000)
    assert st.sections.commissions == Decimal(1000)
    assert st.reserve_balance == Decimal(1200)
    (activity,) = st.activities
    assert activity.category == "Není živností, řídí se zvláštním předpisem"
    assert activity.amount == Decimal(1000)
    assert "Zprostředkování úvěrů" in activity.items


def test_negative_reserve_contribution_and_decimal_payout():
    st = parse_text(make_text(Spec(paid_to_reserve=-4418, released=388, payout=Decimal("1128.47"))))
    assert st.summary.paid_to_reserve == Decimal(-4418)
    assert st.summary.released_from_reserve == Decimal(388)
    assert st.summary.payout == Decimal("1128.47")


def test_multiple_rows_and_activity_categories():
    spec = Spec(
        rows=[
            ("Smyšlená Anna", "111", "Životní", "Pojišťovna A, a.s.", 30000),
            ("Vymyšlený Petr", "222", "Úvěr", "Banka B, a.s.", 2500),
        ],
        activities=[
            ("Není živností, řídí se zvláštním předpisem", ("Zprostředkování pojištění",), 30000),
            ("Živnost volná", (), 2500),
        ],
    )
    st = parse_text(make_text(spec))
    assert st.summary.total == Decimal(32500)
    assert [(a.category, a.amount) for a in st.activities] == [
        ("Není živností, řídí se zvláštním předpisem", Decimal(30000)),
        ("Živnost volná", Decimal(2500)),
    ]


def test_summary_and_table_mimoradne_are_not_confused():
    st = parse_text(make_text(Spec(extraordinary=500)))
    assert st.summary.extraordinary == Decimal(500)
    assert st.sections.extraordinary == Decimal(500)
    assert st.summary.total == Decimal(1500)


def test_extra_whitespace_and_nbsp_are_tolerated():
    text = make_text(Spec()).replace("Provize celkem 1 000 Kč", "Provize celkem   1 000 Kč")
    assert parse_text(text).summary.total == Decimal(1000)


def test_rejects_other_documents():
    with pytest.raises(ParseError, match="Provizní sestava"):
        parse_text("Faktura\nČíslo 2024001\nCelkem 1 000 Kč")


def test_missing_summary_line():
    text = make_text(Spec()).replace("Provize celkem", "Něco jiného")
    with pytest.raises(ParseError, match="Provize celkem"):
        parse_text(text)


def test_missing_period():
    text = make_text(Spec()).replace("Období:", "Obd.")
    with pytest.raises(ParseError, match="period"):
        parse_text(text)


def test_invalid_date():
    text = make_text(Spec()).replace("Období: 1.1.2030", "Období: 31.2.2030")
    with pytest.raises(ParseError, match="invalid date"):
        parse_text(text)


def test_activity_without_amount():
    text = make_text(Spec()).replace("• Zprostředkování investic 1 000 Kč", "• Zprostředkování investic")
    with pytest.raises(ParseError, match="no amount"):
        parse_text(text)


def test_missing_activity_table():
    text = make_text(Spec()).split("Rozdělení příjmů")[0]
    with pytest.raises(ParseError, match="Druh činnosti"):
        parse_text(text)
