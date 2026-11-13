from datetime import date
from decimal import Decimal
from pathlib import Path

from commission_tax_calc.core.grouping import group_invoices, profile_from_group
from commission_tax_calc.core.invoice_models import DocType, Origin
from commission_tax_calc.core.invoice_report import (
    RateSource,
    build_invoice_report,
    detect_my_ico,
    invoice_years,
)
from commission_tax_calc.core.invoice_store import InvoiceStore
from commission_tax_calc.core.invoice_text import parse_invoice_text
from commission_tax_calc.core.isdoc import parse_isdoc
from commission_tax_calc.core.issues import IssueCode, Severity
from commission_tax_calc.core.rules import RulesRepository
from commission_tax_calc.core.tax import UNASSIGNED_INVOICES_LABEL, compute
from factory import CUSTOMER_A, CUSTOMER_B, SUPPLIER_ICO, InvoiceSpec, invoice_text, make_isdoc


def isdoc(name="a", **changes):
    return parse_isdoc(make_isdoc(InvoiceSpec(**changes)), Path(f"{name}.pdf"))


def store(**changes) -> InvoiceStore:
    s = InvoiceStore(None)
    s.my_ico = SUPPLIER_ICO
    for key, value in changes.items():
        setattr(s, key, value)
    return s


def codes(report):
    return {i.code for i in report.all_issues()}


def test_counts_own_invoices_by_payment_year():
    invoices = [
        isdoc("a", number="1", issue=date(2030, 3, 1), due=date(2030, 3, 15)),
        isdoc("b", number="2", issue=date(2030, 12, 20), due=date(2031, 1, 5)),
    ]
    s = store()
    assert invoice_years(invoices, s) == {2030, 2031}
    report = build_invoice_report(invoices, 2030, s)
    assert [r.invoice.number for r in report.counted] == ["1"]
    later = build_invoice_report(invoices, 2031, s)
    assert IssueCode.INVOICE_PAYMENT_UNCONFIRMED in codes(later)


def test_confirmed_payment_date_moves_invoice_and_silences_warning():
    invoice = isdoc(issue=date(2030, 12, 20), due=date(2031, 1, 5))
    s = store(payment_dates={invoice.key: date(2030, 12, 28)})
    report = build_invoice_report([invoice], 2030, s)
    assert len(report.counted) == 1
    assert IssueCode.INVOICE_PAYMENT_UNCONFIRMED not in codes(report)


def test_received_invoices_are_not_counted():
    received = isdoc(supplier_ico="22222227", customer_ico=SUPPLIER_ICO)
    report = build_invoice_report([received], 2030, store())
    assert report.counted == []
    assert IssueCode.INVOICE_RECEIVED in codes(report)


def test_credit_note_subtracts_and_advance_is_skipped():
    invoices = [
        isdoc("a", number="1", lines=[("Práce", 10000)]),
        isdoc("b", number="2", doc_type=2, lines=[("Sleva", 1000)]),
        isdoc("c", number="3", doc_type=4, lines=[("Záloha", 5000)]),
    ]
    s = store(manual_rates={})
    report = build_invoice_report(invoices, 2030, s, {"trades"})
    assert report.rate_income == {"trades": Decimal("9000.00")}
    assert IssueCode.INVOICE_ADVANCE in codes(report)


def test_duplicates_and_conflicts():
    a = isdoc("a", number="1")
    copy = isdoc("a (1)", number="1")  # same UUID
    other = parse_isdoc(make_isdoc(InvoiceSpec(number="1", uuid="other", lines=[("x", 999)])), Path("z.pdf"))
    report = build_invoice_report([a, copy, other], 2030, store(), {"trades"})
    assert len(report.counted) == 1
    assert {IssueCode.INVOICE_DUPLICATE, IssueCode.INVOICE_CONFLICT} <= codes(report)


def test_rate_precedence_manual_group_ares():
    a = isdoc("a", number="1", lines=[("Montáž elektroinstalace", 1000)])
    b = isdoc("b", number="2", lines=[("Montáž elektroinstalace", 2000)])
    group = group_invoices([a])[0]
    s = store(
        manual_rates={a.key: "other_self_employment"},
        profiles=[profile_from_group(group, "crafts_agriculture")],
    )
    report = build_invoice_report([a, b], 2030, s, {"trades"})
    rows = {r.invoice.number: r for r in report.rows}
    assert (rows["1"].rate_id, rows["1"].rate_source) == ("other_self_employment", RateSource.MANUAL)
    assert (rows["2"].rate_id, rows["2"].rate_source) == ("crafts_agriculture", RateSource.GROUP)
    assert IssueCode.INVOICES_AUTO_ASSIGNED in codes(report)


def test_ares_applies_only_when_unambiguous():
    invoice = isdoc()
    assert build_invoice_report([invoice], 2030, store(), {"trades"}).rows[0].rate_source == RateSource.ARES
    ambiguous = build_invoice_report([invoice], 2030, store(), {"trades", "crafts_agriculture"})
    assert ambiguous.rows[0].rate_id is None
    assert ambiguous.unassigned == Decimal("10000.00")
    issue = next(i for i in ambiguous.issues if i.code is IssueCode.INVOICES_UNASSIGNED)
    assert issue.severity is Severity.ERROR


def test_unassigned_income_still_raises_the_tax_base():
    rules, _ = RulesRepository(None).get(2026)
    report = build_invoice_report([isdoc()], 2030, store())
    tax = compute({}, rules, None, report.rate_income, report.unassigned)
    assert tax.unmapped == {UNASSIGNED_INVOICES_LABEL: Decimal("10000.00")}
    assert tax.partial_base == Decimal("10000.00")


def test_invoice_income_merges_with_statements():
    rules, _ = RulesRepository(None).get(2026)
    tax = compute(
        {"Není živností, řídí se zvláštním předpisem": Decimal(1000)},
        rules,
        None,
        {"other_self_employment": Decimal(500), "trades": Decimal(2000)},
    )
    assert [(line.rate.percent, line.income) for line in tax.lines] == [
        (60, Decimal(2000)),
        (40, Decimal(1500)),
    ]


def test_text_invoice_needs_review_until_corrected():
    text = invoice_text(InvoiceSpec())
    invoice = parse_invoice_text(text, Path("t.pdf"), "sha256:x", Origin.TEXT, None).with_changes(
        raw_text=text
    )
    s = store()
    report = build_invoice_report([invoice], 2030, s, {"trades"})
    assert IssueCode.INVOICE_NEEDS_REVIEW in codes(report)
    s.set_correction(invoice, {"amount": Decimal("12345.00"), "doc_type": DocType.INVOICE})
    corrected = build_invoice_report([invoice], 2030, s, {"trades"})
    assert IssueCode.INVOICE_NEEDS_REVIEW not in codes(corrected)
    assert corrected.total == Decimal("12345.00")


def test_number_gaps():
    invoices = [isdoc(str(n), number=f"2030{n:03d}", uuid=str(n)) for n in (1, 2, 4, 5)]
    report = build_invoice_report(invoices, 2030, store(), {"trades"})
    gap = next(i for i in report.issues if i.code is IssueCode.INVOICE_NUMBER_GAP)
    assert gap.params["missing"] == "2030003"


def test_unknown_own_ico_warns_and_counts_all():
    s = InvoiceStore(None)
    report = build_invoice_report([isdoc()], 2030, s)
    assert len(report.counted) == 1
    assert IssueCode.MY_ICO_UNKNOWN in codes(report)


def test_detect_my_ico_prefers_most_frequent_supplier():
    invoices = [isdoc(str(n), uuid=str(n)) for n in range(3)]
    invoices.append(isdoc("r", supplier_ico=CUSTOMER_B[0], customer_ico=SUPPLIER_ICO, uuid="r"))
    assert detect_my_ico(invoices) == SUPPLIER_ICO
    assert CUSTOMER_A  # imported for symmetry with other tests
