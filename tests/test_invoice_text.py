from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from commission_tax_calc.core.ico import is_valid
from commission_tax_calc.core.invoice_models import DocType, Origin
from commission_tax_calc.core.invoice_text import looks_like_invoice, parse_invoice_text
from factory import CUSTOMER_A, SUPPLIER_ICO, InvoiceSpec, invoice_text


def parse(spec: InvoiceSpec, my_ico=SUPPLIER_ICO, text=None):
    return parse_invoice_text(text or invoice_text(spec), Path("f.pdf"), "k", Origin.TEXT, my_ico)


def test_reads_labelled_values():
    inv = parse(InvoiceSpec(lines=[("Montáž rozvaděče", 12000), ("Revize", 3000)]))
    assert inv.needs_review  # heuristics are never trusted blindly
    assert inv.number == "2030001"
    assert (inv.supplier_ico, inv.customer_ico) == (SUPPLIER_ICO, CUSTOMER_A[0])
    assert inv.customer_name == CUSTOMER_A[1]
    assert (inv.issue_date, inv.due_date) == (date(2030, 3, 1), date(2030, 3, 15))
    assert inv.amount == Decimal("15000.00")
    assert not inv.vat_payer
    assert any("rozvaděče" in line.description for line in inv.lines)


def test_ico_split_without_known_ico():
    # The IČO on the "Odběratel" line belongs to the customer even though the
    # two-column layout interleaves the blocks.
    inv = parse(InvoiceSpec(), my_ico=None)
    assert (inv.supplier_ico, inv.customer_ico) == (SUPPLIER_ICO, CUSTOMER_A[0])


def test_vat_payer_uses_amount_without_vat():
    inv = parse(InvoiceSpec(vat=True, lines=[("Práce", 10000)]))
    assert inv.vat_payer
    assert inv.amount == Decimal("10000.00")


@pytest.mark.parametrize(("code", "doc_type"), [(2, DocType.CREDIT_NOTE), (4, DocType.ADVANCE)])
def test_document_type_from_title(code, doc_type):
    assert parse(InvoiceSpec(doc_type=code)).doc_type is doc_type


@pytest.mark.parametrize("phrase", ["Firma není plátcem DPH.", "Neplátce DPH", "Nejsem plátce DPH"])
def test_non_payer_phrases(phrase):
    text = invoice_text(InvoiceSpec()).replace("Firma není plátcem DPH.", phrase)
    assert not parse(InvoiceSpec(), text=text).vat_payer


def test_missing_values_stay_empty():
    inv = parse(None, text="Faktura č. 1\nIČ: 12345679\nNěco nečitelného")
    assert inv.amount is None and inv.due_date is None


def test_looks_like_invoice():
    assert looks_like_invoice(invoice_text(InvoiceSpec()))
    assert not looks_like_invoice("Výpis z účtu\nZůstatek 1 000 Kč")


@pytest.mark.parametrize(
    ("ico", "valid"), [("12345679", True), ("12345678", False), ("19", True), ("abc", False)]
)
def test_ico_checksum(ico, valid):
    assert is_valid(ico) is valid
