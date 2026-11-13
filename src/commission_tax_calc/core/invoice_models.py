"""Data model of an issued invoice.

One class serves all input formats (ISDOC, PDF text, OCR, manual edit), so the
rest of the app never cares where an invoice came from - only whether its
values are *trusted* (``needs_review``).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path


class DocType(str, Enum):
    """Kinds of documents, following the ISDOC ``DocumentType`` code list."""

    INVOICE = "invoice"  # 1 faktura – daňový doklad, 7 zjednodušený daňový doklad
    CREDIT_NOTE = "credit_note"  # 2 opravný daňový doklad (dobropis)
    DEBIT_NOTE = "debit_note"  # 3 opravný daňový doklad (vrubopis)
    ADVANCE = "advance"  # 4 zálohová faktura, 5/6 doklady k záloze

    @property
    def counted(self) -> bool:
        # Advance documents are not counted: the final invoice states the full
        # amount, so counting both would count the income twice.
        return self is not DocType.ADVANCE

    @property
    def sign(self) -> int:
        return -1 if self is DocType.CREDIT_NOTE else 1


class Origin(str, Enum):
    ISDOC = "isdoc"  # structured XML - exact
    TEXT = "text"  # label heuristics on the PDF text layer
    OCR = "ocr"  # label heuristics on OCR output of a scanned PDF


@dataclass(frozen=True)
class InvoiceLine:
    description: str
    amount: Decimal | None = None


@dataclass(frozen=True)
class Invoice:
    source: Path
    origin: Origin
    key: str  # stable identity: ISDOC UUID, or a hash of the file
    number: str | None = None
    doc_type: DocType = DocType.INVOICE
    supplier_ico: str | None = None
    supplier_name: str | None = None
    customer_ico: str | None = None
    customer_name: str | None = None
    issue_date: date | None = None
    tax_point_date: date | None = None  # DUZP
    due_date: date | None = None
    vat_payer: bool = False
    # The income for § 7: for VAT payers the amount *without* VAT. Positive
    # even for credit notes - the sign comes from ``doc_type``.
    amount: Decimal | None = None
    lines: tuple[InvoiceLine, ...] = ()
    note: str = ""
    confirmed: bool = False  # the user reviewed and confirmed the values
    page_count: int = field(default=0, compare=False)
    # Text the values were read from (PDF text or OCR). Kept so the invoice
    # can be re-read cheaply when the user's own IČO becomes known, without
    # running OCR again.
    raw_text: str = field(default="", compare=False, repr=False)

    @property
    def needs_review(self) -> bool:
        return self.origin is not Origin.ISDOC and not self.confirmed

    @property
    def signed_amount(self) -> Decimal | None:
        return None if self.amount is None else self.amount * self.doc_type.sign

    @property
    def description_text(self) -> str:
        """All free text describing *what* was delivered (used for grouping)."""
        return " ".join([self.note, *(line.description for line in self.lines)])

    def with_changes(self, **changes) -> Invoice:
        return replace(self, **changes)


# Fields the user may correct in the review dialog, with their types. Kept
# here (not in the GUI) so the JSON store can validate stored corrections.
EDITABLE_FIELDS: dict[str, type] = {
    "number": str,
    "doc_type": DocType,
    "supplier_ico": str,
    "customer_ico": str,
    "customer_name": str,
    "issue_date": date,
    "tax_point_date": date,
    "due_date": date,
    "amount": Decimal,
    "vat_payer": bool,
}
