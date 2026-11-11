"""Immutable data classes describing one parsed commission statement.

All classes are ``frozen`` dataclasses: once a PDF is parsed the result must
never change, so it can be shared safely between the worker thread that parses
files and the GUI thread that displays them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True, order=True)
class Period:
    """Statement period, both ends inclusive (e.g. 1.1.2026 - 14.1.2026)."""

    start: date
    end: date

    def __str__(self) -> str:
        return f"{_cz_date(self.start)} – {_cz_date(self.end)}"

    def overlaps(self, other: Period) -> bool:
        return self.start <= other.end and other.start <= self.end

    def next_day(self) -> date:
        return self.end + timedelta(days=1)


def _cz_date(d: date) -> str:
    return f"{d.day}.{d.month}.{d.year}"


@dataclass(frozen=True)
class Summary:
    """The "Shrnutí" block at the top of the statement."""

    regular: Decimal  # Provize za běžné období
    extraordinary: Decimal  # Mimořádné provize
    total: Decimal  # Provize celkem  <- the taxable amount
    released_from_reserve: Decimal  # Uvolněno ze stornofondu
    paid_to_reserve: Decimal  # Odvedeno do stornofondu (printed as negative)
    payout: Decimal  # K výplatě


@dataclass(frozen=True)
class SectionTotals:
    """The "Celkem" rows of the detail tables, used for cross-checks."""

    commissions: Decimal  # Provize
    inter_commissions: Decimal  # Meziprovize
    holding: Decimal  # Holdingové provize
    extraordinary: Decimal  # Mimořádné provize
    deductions: Decimal  # Exekuce a srážky


@dataclass(frozen=True)
class ActivityIncome:
    """One row of "Rozdělení příjmů pro uplatnění paušálních výdajů".

    ``category`` is the heading (e.g. "Není živností, řídí se zvláštním
    předpisem"); ``items`` are the bullet points listed under it. The category
    text is what decides the flat-rate expense percentage.
    """

    category: str
    items: tuple[str, ...]
    amount: Decimal


@dataclass(frozen=True)
class Statement:
    source: Path
    holder: str
    period: Period
    summary: Summary
    sections: SectionTotals
    activities: tuple[ActivityIncome, ...]
    reserve_balance: Decimal | None = None  # Stornofond celkem - current value
    page_count: int = field(default=0, compare=False)
