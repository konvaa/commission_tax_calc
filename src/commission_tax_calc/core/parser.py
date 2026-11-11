"""Turns a FinTrust "Provizní sestava" PDF into a :class:`Statement`.

The work is split into two steps on purpose:

1. :func:`extract_text` - the only function that touches the PDF library.
2. :func:`parse_text` - a pure function ``str -> Statement``.

Because step 2 is pure, almost all tests run on plain text fixtures with
fictitious clients. Real statements contain client names and contract numbers
and must never end up in the repository (GDPR).

Why the parser reads *labels* and *section totals* instead of every table row:
in the extracted text, table columns are separated only by spaces, so a row
like ``"… 9,5 100 950 Kč"`` (points, CZK per point, commission) is ambiguous -
it can be read as commission ``950`` or ``100 950``. Labelled lines
("Provize celkem 741 Kč") and the "Celkem" lines of each table have no such
ambiguity, and comparing them against each other still detects a misread file
(see ``validation.py``).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from .models import ActivityIncome, Period, SectionTotals, Statement, Summary
from .money import AMOUNT_PATTERN, parse_czk, trailing_czk


class ParseError(ValueError):
    """The file is not a commission statement in the expected format."""


_PERIOD_RE = re.compile(
    r"Období:\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\s*[-–]\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})"
)

# Summary labels -> Summary field names.
_SUMMARY_LABELS = {
    "Provize za běžné období": "regular",
    "Mimořádné provize": "extraordinary",
    "Provize celkem": "total",
    "Uvolněno ze stornofondu": "released_from_reserve",
    "Odvedeno do stornofondu": "paid_to_reserve",
    "K výplatě": "payout",
}

# Detail table headings (a line containing exactly this text) -> field names.
_SECTION_HEADINGS = {
    "Provize": "commissions",
    "Meziprovize": "inter_commissions",
    "Holdingové provize": "holding",
    "Mimořádné provize": "extraordinary",
    "Exekuce a srážky": "deductions",
}

_ACTIVITY_HEADER = "Druh činnosti"
_BULLETS = "•●▪◦-*"


def extract_text(path: Path) -> tuple[str, int]:
    """Return the text of all pages and the page count.

    ``pdfplumber`` is imported lazily so that the pure parsing functions (and
    their tests) do not pay its import cost.
    """
    import pdfplumber

    try:
        with pdfplumber.open(path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
    except Exception as exc:  # pdfplumber raises many different exception types
        raise ParseError(f"cannot open PDF ({exc.__class__.__name__}: {exc})") from exc
    return "\n".join(pages), len(pages)


def parse_file(path: Path) -> Statement:
    text, pages = extract_text(path)
    statement = parse_text(text, source=path)
    # dataclasses.replace would also work; a direct constructor call keeps the
    # frozen dataclass explicit about what changes.
    return Statement(
        source=statement.source,
        holder=statement.holder,
        period=statement.period,
        summary=statement.summary,
        sections=statement.sections,
        activities=statement.activities,
        reserve_balance=statement.reserve_balance,
        page_count=pages,
    )


def parse_text(text: str, source: Path | None = None) -> Statement:
    lines = [_normalize(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not any(line.startswith("Provizní sestava") for line in lines[:5]):
        raise ParseError("missing heading 'Provizní sestava'")

    period, period_index = _parse_period(lines)
    holder = lines[period_index + 1] if period_index + 1 < len(lines) else ""

    return Statement(
        source=source or Path("<text>"),
        holder=holder,
        period=period,
        summary=_parse_summary(lines),
        sections=_parse_sections(lines),
        activities=_parse_activities(lines),
        reserve_balance=_parse_reserve_balance(lines),
    )


# ---------------------------------------------------------------- helpers ---


def _normalize(line: str) -> str:
    # Collapse runs of whitespace (layout padding, no-break spaces between
    # words) but keep single spaces, which act as thousands separators.
    return re.sub(r"[ \t  ]+", " ", line).strip()


def _parse_period(lines: list[str]) -> tuple[Period, int]:
    for index, line in enumerate(lines):
        match = _PERIOD_RE.search(line)
        if match:
            d1, m1, y1, d2, m2, y2 = map(int, match.groups())
            try:
                period = Period(date(y1, m1, d1), date(y2, m2, d2))
            except ValueError as exc:
                raise ParseError(f"invalid date in period: {line!r}") from exc
            if period.end < period.start:
                raise ParseError(f"period ends before it starts: {line!r}")
            return period, index
    raise ParseError("period ('Období: …') not found")


def _parse_summary(lines: list[str]) -> Summary:
    values: dict[str, Decimal] = {}
    # The summary is the first block of the statement; stop at the first detail
    # table so "Mimořádné provize" is not confused with its later table.
    for line in lines:
        if line in _SECTION_HEADINGS:
            break
        split = trailing_czk(line)
        if split is None:
            continue
        label, amount = split
        field_name = _SUMMARY_LABELS.get(label)
        if field_name and field_name not in values:
            values[field_name] = amount
    missing = [label for label, name in _SUMMARY_LABELS.items() if name not in values]
    if missing:
        raise ParseError("summary is missing: " + ", ".join(missing))
    return Summary(**values)


def _parse_sections(lines: list[str]) -> SectionTotals:
    values: dict[str, Decimal] = {}
    current: str | None = None
    for line in lines:
        if line in _SECTION_HEADINGS:
            current = _SECTION_HEADINGS[line]
            continue
        if current and line.startswith("Celkem"):
            split = trailing_czk(line)
            if split is not None:
                values.setdefault(current, split[1])
                current = None
    missing = [heading for heading, name in _SECTION_HEADINGS.items() if name not in values]
    if missing:
        raise ParseError("table totals missing for: " + ", ".join(missing))
    return SectionTotals(**values)


def _parse_activities(lines: list[str]) -> tuple[ActivityIncome, ...]:
    """Parse the "Rozdělení příjmů … dle § 7 odst. 7" table.

    Layout in the extracted text::

        Druh činnosti Provize
        Není živností, řídí se zvláštním předpisem      <- category heading
        • Zprostředkování pojištění                     <- bullet items
        • Zprostředkování investic 741 Kč               <- amount sits on a
        • …                                                 *middle* line

    A non-bullet line starts a new category; an amount anywhere inside the
    category's block belongs to that category.
    """
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith(_ACTIVITY_HEADER))
    except StopIteration:
        raise ParseError("income split by activity ('Druh činnosti') not found") from None

    blocks: list[dict] = []
    for line in lines[start + 1 :]:
        split = trailing_czk(line)
        text, amount = (split[0], split[1]) if split else (line, None)
        is_bullet = text[:1] in _BULLETS
        if is_bullet and blocks:
            blocks[-1]["items"].append(text.lstrip(_BULLETS + " "))
        else:
            if text.startswith("Celkem"):
                # Some layouts may print an overall total row; it is not a category.
                continue
            blocks.append({"category": text, "items": [], "amount": None})
        if amount is not None:
            if blocks[-1]["amount"] is not None:
                raise ParseError(f"two amounts for activity {blocks[-1]['category']!r}")
            blocks[-1]["amount"] = amount

    activities = []
    for block in blocks:
        if block["amount"] is None:
            raise ParseError(f"no amount for activity {block['category']!r}")
        activities.append(ActivityIncome(block["category"], tuple(block["items"]), block["amount"]))
    if not activities:
        raise ParseError("income split by activity is empty")
    return tuple(activities)


def _parse_reserve_balance(lines: list[str]) -> Decimal | None:
    # "Stornofond celkem 18 845 Kč 18 457 Kč -388 Kč" -> previous, current, change.
    for line in lines:
        if line.startswith("Stornofond celkem"):
            amounts = re.findall(rf"({AMOUNT_PATTERN})\s*Kč", line)
            if len(amounts) >= 2:
                return parse_czk(amounts[1])
    return None
