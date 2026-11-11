from decimal import Decimal

import pytest

from commission_tax_calc.core.money import AmountError, format_czk, parse_czk, trailing_czk


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("741 Kč", "741"),
        ("1 128,47 Kč", "1128.47"),
        ("-4 418 Kč", "-4418"),
        ("125 632 Kč", "125632"),  # no-break spaces from the PDF
        ("−388", "-388"),  # typographic minus
        ("0", "0"),
    ],
)
def test_parse_czk(text, expected):
    assert parse_czk(text) == Decimal(expected)


def test_parse_czk_rejects_garbage():
    with pytest.raises(AmountError):
        parse_czk("abc Kč")


@pytest.mark.parametrize(
    ("line", "label", "amount"),
    [
        ("Provize celkem 741 Kč", "Provize celkem", "741"),
        ("K výplatě 1 128,47 Kč", "K výplatě", "1128.47"),
        ("Odvedeno do stornofondu -4 418 Kč", "Odvedeno do stornofondu", "-4418"),
        # Kč/bod "112.5" must not glue its last digit to the amount ("5 741").
        ("Makowski 235979914 Můj Domov 10973 N 6,6 112.5 741 Kč", None, "741"),
        ("Celkem 23,7 2 368 Kč", "Celkem 23,7", "2368"),
    ],
)
def test_trailing_czk(line, label, amount):
    found_label, found_amount = trailing_czk(line)
    assert found_amount == Decimal(amount)
    if label is not None:
        assert found_label == label


def test_trailing_czk_without_amount():
    assert trailing_czk("• Zprostředkování pojištění") is None


def test_format_czk():
    assert format_czk(Decimal("1128.47"), 2) == "1 128,47 Kč"
    assert format_czk(Decimal("86661")) == "86 661 Kč"
    assert format_czk(Decimal("-4418")) == "-4 418 Kč"
    assert format_czk(Decimal("0")) == "0 Kč"
    assert format_czk(Decimal("999.5")) == "1 000 Kč"  # half-up rounding
