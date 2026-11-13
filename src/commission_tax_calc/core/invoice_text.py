"""Best-effort reading of an invoice from plain text (PDF text layer or OCR).

Invoices without ISDOC have no common layout, so this module looks for the
labels every Czech invoice must carry by law (IČ, dates, total) instead of
positions. The result is always marked *needs review*: the user confirms the
values in the review dialog, with the PDF shown next to them. Heuristics are
good at saving typing; they are not trusted for a tax return.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from pathlib import Path

from .invoice_models import DocType, Invoice, InvoiceLine, Origin
from .money import parse_czk

# Amount with optional decimals: "163 825,00", "1.234,50" is not Czech, ignore.
_AMOUNT = r"[-−]?\d{1,3}(?:[   ]?\d{3})*(?:[,.]\d{2})?"
_DATE = r"(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})"
_ICO = re.compile(r"\bIČO?\s*:?\s*(\d{8})\b", re.IGNORECASE)

_ISSUE = re.compile(rf"datum\s+vystavení\s*:?\s*{_DATE}", re.IGNORECASE)
_DUE = re.compile(rf"(?:datum\s+)?splatnost[i]?\s*:?\s*{_DATE}", re.IGNORECASE)
_TAX_POINT = re.compile(
    rf"(?:DUZP|datum\s+(?:uskutečnění\s+)?(?:zdanitelného\s+)?plnění)\s*:?\s*{_DATE}", re.IGNORECASE
)
_NUMBER = re.compile(
    r"(?:faktura|daňový\s+doklad|dobropis|číslo\s+faktury|číslo\s+dokladu)"
    r"(?:\s*[-–]\s*daňový\s+doklad)?\s*(?:č\.|číslo)?\s*:?\s*([A-Z0-9][A-Z0-9/\-]{2,})",
    re.IGNORECASE,
)
_TOTAL_LABELS = re.compile(
    r"(celkem\s+k\s+úhradě|k\s+úhradě|celkem\s+k\s+zaplacení|částka\s+k\s+úhradě)", re.IGNORECASE
)
_WITHOUT_VAT = re.compile(r"(celkem\s+bez\s+DPH|základ\s+DPH\s+celkem|součet\s+bez\s+DPH)", re.IGNORECASE)
# "není plátcem DPH", "nejsem plátce DPH", "neplátce DPH", "Neplátce DPH"…
_NON_PAYER = re.compile(r"(\bne(ní|jsem|jsme)?\s*plátc\w*|neplátce)\s+DPH", re.IGNORECASE)
_CREDIT = re.compile(r"\b(dobropis|opravný\s+daňový\s+doklad)\b", re.IGNORECASE)
_ADVANCE = re.compile(r"\b(zálohová\s+faktura|výzva\s+k\s+platbě|proforma)\b", re.IGNORECASE)
_LINES_START = re.compile(r"(označení\s+dodávky|popis\s+položky|položka|předmět\s+plnění|popis)\b", re.I)
_LINES_END = re.compile(r"^(součet|celkem|mezisoučet|zaokrouhlení)", re.IGNORECASE)
_INVOICE_WORDS = re.compile(r"\b(faktura|daňový\s+doklad|dobropis)\b", re.IGNORECASE)


def looks_like_invoice(text: str) -> bool:
    return bool(_INVOICE_WORDS.search(text)) and bool(_ICO.search(text))


def parse_invoice_text(
    text: str,
    source: Path,
    key: str,
    origin: Origin = Origin.TEXT,
    my_ico: str | None = None,
    page_count: int = 0,
) -> Invoice:
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    supplier, customer = _split_icos(lines, my_ico)
    vat_payer = not _NON_PAYER.search(text) and bool(re.search(r"\bDPH\b", text))
    amount = _labelled_amount(lines, _WITHOUT_VAT) if vat_payer else None
    if amount is None:
        amount = _labelled_amount(lines, _TOTAL_LABELS)

    doc_type = DocType.INVOICE
    if _ADVANCE.search(text):
        doc_type = DocType.ADVANCE
    elif _CREDIT.search(text):
        doc_type = DocType.CREDIT_NOTE

    number_match = _NUMBER.search(text)
    return Invoice(
        source=source,
        origin=origin,
        key=key,
        number=number_match.group(1) if number_match else None,
        doc_type=doc_type,
        supplier_ico=supplier,
        customer_ico=customer,
        customer_name=_customer_name(lines),
        issue_date=_find_date(_ISSUE, text),
        tax_point_date=_find_date(_TAX_POINT, text),
        due_date=_find_date(_DUE, text),
        vat_payer=vat_payer,
        amount=abs(amount) if amount is not None else None,
        lines=tuple(InvoiceLine(d) for d in _item_descriptions(lines)),
        page_count=page_count,
    )


# ---------------------------------------------------------------- helpers ---


def _find_date(pattern: re.Pattern, text: str) -> date | None:
    match = pattern.search(text)
    if not match:
        return None
    day, month, year = (int(g) for g in match.groups()[-3:])
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _labelled_amount(lines: list[str], label: re.Pattern) -> Decimal | None:
    """Last amount on the last line carrying the label.

    "Last" in both cases: totals sit at the bottom of the invoice and the
    amount at the end of the row ("CELKEM K ÚHRADĚ Částky jsou v Kč 163 825,00").
    """
    for line in reversed(lines):
        if label.search(line):
            amounts = re.findall(rf"(?<![\d,.]){_AMOUNT}(?![\d])", line[label.search(line).end() :])
            if amounts:
                try:
                    return parse_czk(amounts[-1].replace(".", ","))
                except ValueError:
                    return None
    return None


def _split_icos(lines: list[str], my_ico: str | None) -> tuple[str | None, str | None]:
    """Decide which IČO is the supplier and which the customer.

    1. If the user's own IČO is known and present, it is the supplier.
    2. Otherwise an IČO on a line mentioning "Odběratel" belongs to the
       customer and the first other IČO is the supplier.
    """
    found: list[tuple[str, bool]] = []
    found_lines: list[tuple[str, str]] = []
    customer_block = False
    for line in lines:
        lowered = line.lower()
        if "odběratel" in lowered:
            customer_block = True
        elif "dodavatel" in lowered:
            customer_block = False
        for match in _ICO.finditer(line):
            on_customer_line = "odběratel" in lowered or (customer_block and "dodavatel" not in lowered)
            found.append((match.group(1), on_customer_line))
            found_lines.append((match.group(1), line))
    icos = _unique(ico for ico, _ in found)
    if my_ico and my_ico in icos:
        others = [i for i in icos if i != my_ico]
        return my_ico, others[0] if others else None
    # An IČO on the very line saying "Odběratel" is certain; the block-based
    # guess is a fallback, because two-column layouts interleave the
    # supplier's and the customer's lines in the extracted text.
    same_line = [ico for ico, line in found_lines if "odběratel" in line.lower()]
    customers = same_line or [ico for ico, is_customer in found if is_customer]
    customer = customers[0] if customers else None
    supplier = next((i for i in icos if i != customer), None)
    if customer is None:
        customer = next((i for i in icos if i != supplier), None)
    return supplier, customer


def _customer_name(lines: list[str]) -> str | None:
    # The customer's name is usually the first line after "Odběratel" that is
    # not a label (IČ/DIČ) - good enough as a hint, the user can correct it.
    for index, line in enumerate(lines):
        if "odběratel" in line.lower():
            for candidate in lines[index + 1 : index + 6]:
                if not re.match(r"^(DIČ|IČO?|Odběratel)\b", candidate, re.IGNORECASE):
                    return candidate
    return None


def _item_descriptions(lines: list[str]) -> list[str]:
    start = next((i for i, line in enumerate(lines) if _LINES_START.search(line)), None)
    if start is None:
        return []
    result = []
    for line in lines[start + 1 :]:
        if _LINES_END.match(line):
            break
        # Drop quantities and prices, keep the description words.
        description = re.sub(rf"\s+\d+([,.]\d+)?\s*(ks|h|hod|m|kg|km|x)?\s+{_AMOUNT}.*$", "", line)
        description = re.sub(rf"\s+{_AMOUNT}(\s+{_AMOUNT})*\s*$", "", description)
        if description:
            result.append(description)
    return result


def _unique(items: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen
