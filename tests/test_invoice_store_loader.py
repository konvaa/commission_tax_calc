from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from commission_tax_calc.core import ocr as ocr_module
from commission_tax_calc.core.grouping import GroupProfile
from commission_tax_calc.core.invoice_models import DocType, Invoice, Origin
from commission_tax_calc.core.invoice_store import InvoiceStore
from commission_tax_calc.core.issues import IssueCode
from commission_tax_calc.core.loader import find_documents, load_documents
from commission_tax_calc.core.ocr import OcrUnavailable
from factory import InvoiceSpec, Spec, find_font, make_invoice_pdf, make_pdf, make_scanned_pdf, make_text


def test_store_roundtrip(tmp_path):
    path = tmp_path / "sub" / "invoices.json"
    store = InvoiceStore(path)
    store.my_ico = "12345679"
    store.payment_dates["k1"] = date(2030, 1, 5)
    store.manual_rates["k1"] = "trades"
    store.profiles.append(
        GroupProfile("33333335", frozenset({"montáž", "revize"}), "crafts_agriculture", "A")
    )
    invoice = Invoice(source=Path("a.pdf"), origin=Origin.TEXT, key="k1")
    store.set_correction(
        invoice, {"amount": Decimal("10.50"), "doc_type": DocType.CREDIT_NOTE, "due_date": date(2030, 1, 2)}
    )
    store.save()
    assert list(path.parent.iterdir()) == [path]  # no temporary file left behind

    loaded = InvoiceStore.load(path)
    assert loaded.my_ico == "12345679"
    assert loaded.payment_dates == {"k1": date(2030, 1, 5)}
    assert loaded.profiles == store.profiles
    corrected = loaded.apply(invoice)
    assert corrected.confirmed and not corrected.needs_review
    assert (corrected.amount, corrected.doc_type, corrected.due_date) == (
        Decimal("10.50"),
        DocType.CREDIT_NOTE,
        date(2030, 1, 2),
    )


def test_corrupt_store_starts_empty(tmp_path):
    path = tmp_path / "invoices.json"
    path.write_text("{broken", "utf-8")
    assert InvoiceStore.load(path).my_ico is None


FONT = find_font()
needs_font = pytest.mark.skipif(FONT is None, reason="no TTF font with Czech glyphs found")


@needs_font
def test_loader_classifies_documents(tmp_path):
    make_pdf(tmp_path / "sestava.pdf", make_text(Spec()), FONT)
    make_invoice_pdf(tmp_path / "isdoc.pdf", InvoiceSpec(number="2030001"), FONT)
    make_invoice_pdf(tmp_path / "text.pdf", InvoiceSpec(number="2030002"), FONT, embed_isdoc=False)
    make_scanned_pdf(tmp_path / "scan.pdf", InvoiceSpec(number="2030003"), FONT)
    make_pdf(tmp_path / "other.pdf", "Pozvánka na schůzi\n" * 10, FONT)
    (tmp_path / "notes.txt").write_text("x")

    from factory import invoice_text

    fake_ocr = lambda path: invoice_text(InvoiceSpec(number="2030003"))  # noqa: E731
    result = load_documents(find_documents(tmp_path), ocr=fake_ocr)
    assert len(result.statements) == 1
    origins = {inv.number: inv.origin for inv in result.invoices}
    assert origins == {"2030001": Origin.ISDOC, "2030002": Origin.TEXT, "2030003": Origin.OCR}
    assert [i.code for i in result.failures] == [IssueCode.UNKNOWN_DOCUMENT]


@needs_font
def test_scan_without_ocr_is_still_listed(tmp_path):
    make_scanned_pdf(tmp_path / "scan.pdf", InvoiceSpec(), FONT)

    def no_ocr(path):
        raise OcrUnavailable("Tesseract OCR is not installed")

    result = load_documents([tmp_path / "scan.pdf"], ocr=no_ocr)
    assert len(result.invoices) == 1
    assert result.invoices[0].needs_review
    assert result.failures[0].code is IssueCode.OCR_UNAVAILABLE


def _tesseract_with_czech() -> bool:
    found = ocr_module.find_tesseract()
    if found is None:
        return False
    try:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = found[0]
        return "ces" in pytesseract.get_languages()
    except Exception:
        return False


@needs_font
@pytest.mark.skipif(not _tesseract_with_czech(), reason="Tesseract with Czech data not installed")
def test_real_ocr_of_scanned_invoice(tmp_path):
    scan = make_scanned_pdf(
        tmp_path / "scan.pdf", InvoiceSpec(number="2030777", lines=[("Zednické práce", 23456)]), FONT
    )
    invoice = load_documents([scan]).invoices[0]
    assert invoice.origin is Origin.OCR
    assert invoice.number == "2030777"
    assert invoice.amount == Decimal("23456.00")
