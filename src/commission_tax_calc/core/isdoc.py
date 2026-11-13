"""ISDOC - the Czech standard for machine-readable invoices.

ISDOC is an XML file (``.isdoc``), optionally zipped with attachments
(``.isdocx``), and many invoicing systems (Pohoda, Money, iDoklad, Fakturoid…)
embed it in the PDF they send. When present it is the most reliable source:
no guessing from layout or OCR.

Parsing is namespace-agnostic (matches local element names), because the
namespace URI changes between ISDOC versions (5.x, 6.x) while the element
names relevant here stay the same.
"""

from __future__ import annotations

import hashlib
import io
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .invoice_models import DocType, Invoice, InvoiceLine, Origin

_MAX_XML_BYTES = 5 * 1024 * 1024

# ISDOC DocumentType code list -> our document types.
_DOC_TYPES = {
    "1": DocType.INVOICE,
    "2": DocType.CREDIT_NOTE,
    "3": DocType.DEBIT_NOTE,
    "4": DocType.ADVANCE,
    "5": DocType.ADVANCE,
    "6": DocType.ADVANCE,
    "7": DocType.INVOICE,
}


class IsdocError(ValueError):
    """The ISDOC content is malformed or not an invoice."""


def file_key(data: bytes) -> str:
    """Identity for documents without a UUID: the hash of the file content.

    A content hash survives renaming and moving the file, and the same file
    downloaded twice gets the same key - exactly what duplicate detection and
    remembering the user's corrections need.
    """
    return "sha256:" + hashlib.sha256(data).hexdigest()[:32]


def extract_from_pdf(path: Path) -> bytes | None:
    """Return the embedded ISDOC XML of a PDF, or ``None``.

    pypdfium2 is already a dependency of pdfplumber, so no new library is
    needed to read PDF attachments.
    """
    import pypdfium2

    try:
        pdf = pypdfium2.PdfDocument(str(path))
    except pypdfium2.PdfiumError:
        return None
    try:
        for index in range(pdf.count_attachments()):
            attachment = pdf.get_attachment(index)
            name = attachment.get_name().lower()
            if name.endswith(".isdoc"):
                return bytes(attachment.get_data())
            if name.endswith(".isdocx"):
                return _xml_from_isdocx(bytes(attachment.get_data()))
    finally:
        pdf.close()
    return None


def read_isdoc_file(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix.lower() == ".isdocx":
        return _xml_from_isdocx(data)
    return data


def _xml_from_isdocx(data: bytes) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name in archive.namelist():
                if name.lower().endswith(".isdoc"):
                    info = archive.getinfo(name)
                    if info.file_size > _MAX_XML_BYTES:
                        raise IsdocError("ISDOC inside ISDOCX is too large")
                    return archive.read(name)
    except zipfile.BadZipFile as exc:
        raise IsdocError("invalid ISDOCX archive") from exc
    raise IsdocError("no .isdoc file inside ISDOCX")


def parse_isdoc(xml: bytes, source: Path, page_count: int = 0) -> Invoice:
    if len(xml) > _MAX_XML_BYTES:
        raise IsdocError("ISDOC file is too large")
    try:
        # The standard library parser does not resolve external entities, and
        # current expat versions limit entity expansion ("billion laughs"),
        # so parsing an untrusted invoice is safe without extra libraries.
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise IsdocError(f"invalid XML: {exc}") from exc
    if _local(root.tag) != "Invoice":
        raise IsdocError("root element is not <Invoice>")

    doc_type = _DOC_TYPES.get(_text(root, "DocumentType") or "1")
    if doc_type is None:
        raise IsdocError(f"unknown DocumentType {_text(root, 'DocumentType')!r}")

    supplier = _child(root, "AccountingSupplierParty")
    customer = _child(root, "AccountingCustomerParty")
    totals = _child(root, "LegalMonetaryTotal")
    vat_payer = (_text(root, "VATApplicable") or "false").strip().lower() == "true"

    # Income for § 7 is the amount without VAT. For non-payers both amounts
    # are equal, so one rule covers everyone.
    amount = _decimal(_text(totals, "TaxExclusiveAmount")) if totals is not None else None
    if amount is None and totals is not None:
        amount = _decimal(_text(totals, "PayableAmount"))

    lines = tuple(
        InvoiceLine(
            description=_text(_child(line, "Item"), "Description") or "",
            amount=_decimal(_text(line, "LineExtensionAmount")),
        )
        for line in _children(_child(root, "InvoiceLines"), "InvoiceLine")
    )
    uuid = _text(root, "UUID")
    payment = _find_path(root, ["PaymentMeans", "Payment", "Details"])

    return Invoice(
        source=source,
        origin=Origin.ISDOC,
        key=f"uuid:{uuid.lower()}" if uuid else file_key(xml),
        number=_text(root, "ID"),
        doc_type=doc_type,
        supplier_ico=_party_ico(supplier),
        supplier_name=_party_name(supplier),
        customer_ico=_party_ico(customer),
        customer_name=_party_name(customer),
        issue_date=_date(_text(root, "IssueDate")),
        tax_point_date=_date(_text(root, "TaxPointDate")),
        due_date=_date(_text(payment, "PaymentDueDate")) if payment is not None else None,
        vat_payer=vat_payer,
        amount=abs(amount) if amount is not None else None,
        lines=lines,
        note=_text(root, "Note") or "",
        page_count=page_count,
    )


# ------------------------------------------------------------- helpers ---


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(element: ET.Element | None, name: str) -> ET.Element | None:
    if element is None:
        return None
    return next((c for c in element if _local(c.tag) == name), None)


def _children(element: ET.Element | None, name: str) -> list[ET.Element]:
    return [] if element is None else [c for c in element if _local(c.tag) == name]


def _find_path(element: ET.Element, names: list[str]) -> ET.Element | None:
    current: ET.Element | None = element
    for name in names:
        current = _child(current, name)
    return current


def _text(element: ET.Element | None, name: str) -> str | None:
    child = _child(element, name)
    if child is None or child.text is None:
        return None
    return child.text.strip() or None


def _party_ico(party_wrapper: ET.Element | None) -> str | None:
    ico = _text(
        _find_path(party_wrapper, ["Party", "PartyIdentification"]) if party_wrapper is not None else None,
        "ID",
    )
    return ico.replace(" ", "") if ico else None


def _party_name(party_wrapper: ET.Element | None) -> str | None:
    if party_wrapper is None:
        return None
    return _text(_find_path(party_wrapper, ["Party", "PartyName"]), "Name")


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
