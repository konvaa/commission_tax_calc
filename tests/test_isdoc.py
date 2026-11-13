import io
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from commission_tax_calc.core.invoice_models import DocType, Origin
from commission_tax_calc.core.isdoc import IsdocError, extract_from_pdf, parse_isdoc, read_isdoc_file
from factory import CUSTOMER_A, SUPPLIER_ICO, InvoiceSpec, find_font, make_invoice_pdf, make_isdoc


def parse(spec: InvoiceSpec):
    return parse_isdoc(make_isdoc(spec), Path("x.isdoc"))


def test_reads_all_fields():
    inv = parse(InvoiceSpec(lines=[("Zednické práce", 15000), ("Materiál", 2500)]))
    assert inv.origin is Origin.ISDOC
    assert not inv.needs_review
    assert inv.number == "2030001"
    assert inv.supplier_ico == SUPPLIER_ICO
    assert (inv.customer_ico, inv.customer_name) == CUSTOMER_A
    assert (inv.issue_date, inv.due_date) == (date(2030, 3, 1), date(2030, 3, 15))
    assert inv.amount == Decimal("17500.00")
    assert [line.description for line in inv.lines] == ["Zednické práce", "Materiál"]
    assert inv.key.startswith("uuid:")


def test_vat_payer_income_is_without_vat():
    inv = parse(InvoiceSpec(vat=True, lines=[("Práce", 10000)]))
    assert inv.vat_payer
    assert inv.amount == Decimal("10000.00")  # not 12 100


@pytest.mark.parametrize(
    ("code", "doc_type", "sign"),
    [
        (1, DocType.INVOICE, 1),
        (2, DocType.CREDIT_NOTE, -1),
        (3, DocType.DEBIT_NOTE, 1),
        (4, DocType.ADVANCE, 1),
    ],
)
def test_document_types(code, doc_type, sign):
    inv = parse(InvoiceSpec(doc_type=code))
    assert inv.doc_type is doc_type
    assert inv.signed_amount == Decimal(10000) * sign


def test_namespace_independent():
    xml = make_isdoc(InvoiceSpec()).replace(
        b"http://isdoc.cz/namespace/2013", b"http://isdoc.cz/namespace/2010"
    )
    assert parse_isdoc(xml, Path("x")).number == "2030001"


@pytest.mark.parametrize(
    "xml", [b"not xml", b"<Faktura/>", b"<Invoice><DocumentType>99</DocumentType></Invoice>"]
)
def test_rejects_invalid(xml):
    with pytest.raises(IsdocError):
        parse_isdoc(xml, Path("x"))


def test_isdocx_archive(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("faktura.isdoc", make_isdoc(InvoiceSpec(number="X1")))
        archive.writestr("priloha.pdf", b"%PDF")
    path = tmp_path / "f.isdocx"
    path.write_bytes(buffer.getvalue())
    assert parse_isdoc(read_isdoc_file(path), path).number == "X1"


FONT = find_font()


@pytest.mark.skipif(FONT is None, reason="no TTF font with Czech glyphs found")
def test_embedded_in_pdf(tmp_path):
    pdf = make_invoice_pdf(tmp_path / "f.pdf", InvoiceSpec(number="E1"), FONT)
    assert parse_isdoc(extract_from_pdf(pdf), pdf).number == "E1"
    plain = make_invoice_pdf(tmp_path / "plain.pdf", InvoiceSpec(), FONT, embed_isdoc=False)
    assert extract_from_pdf(plain) is None
