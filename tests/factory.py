"""Synthetic commission statements for tests.

Real statements contain client names and contract numbers, so they must never
be committed (GDPR). This module produces text in exactly the shape that
pdfplumber extracts from a real FinTrust statement, with invented people and
numbers. ``make_pdf`` renders the same text into a PDF for end-to-end tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

DEFAULT_ACTIVITY = (
    "Není živností, řídí se zvláštním předpisem",
    (
        "Zprostředkování pojištění",
        "Zprostředkování investic",
        "Zprostředkování doplňkového penzijního spoření (III. pilíř důchodové reformy)",
        "Zprostředkování úvěrů",
    ),
)


def czk(value: Decimal | int | str) -> str:
    """Format like the statement: '1 128,47 Kč', '-4 418 Kč' (normal spaces)."""
    value = Decimal(str(value))
    sign = "-" if value < 0 else ""
    integer, _, fraction = f"{abs(value):f}".partition(".")
    groups = []
    while integer:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    text = " ".join(groups) or "0"
    if fraction and fraction.strip("0"):
        text += "," + fraction[:2].ljust(2, "0")
    return f"{sign}{text} Kč"


@dataclass
class Spec:
    start: date = date(2030, 1, 1)
    end: date = date(2030, 1, 14)
    holder: str = "Testovací Tomáš"
    # rows: (client, contract, product, partner, commission)
    rows: list[tuple[str, str, str, str, int]] = field(
        default_factory=lambda: [
            ("Fiktivní Klára", "1000000001", "Domácnost Plus", "Vymyšlená pojišťovna, a.s.", 1000)
        ]
    )
    inter_commissions: int = 0
    holding: int = 0
    extraordinary: int = 0
    deductions: int = 0
    released: int = 0
    paid_to_reserve: int = 0
    payout: Decimal | None = None
    # activities: (heading, bullet items, amount); None = everything in DEFAULT_ACTIVITY
    activities: list[tuple[str, tuple[str, ...], int]] | None = None
    total_override: int | None = None

    @property
    def commissions(self) -> int:
        return sum(r[4] for r in self.rows)

    @property
    def regular(self) -> int:
        return self.commissions + self.inter_commissions + self.holding

    @property
    def total(self) -> int:
        if self.total_override is not None:
            return self.total_override
        return self.regular + self.extraordinary


def make_text(spec: Spec | None = None, **changes) -> str:
    spec = spec or Spec(**changes)
    payout = spec.payout
    if payout is None:
        payout = Decimal(spec.total + spec.released + spec.paid_to_reserve - spec.deductions)
    activities = spec.activities
    if activities is None:
        activities = [(DEFAULT_ACTIVITY[0], DEFAULT_ACTIVITY[1], spec.total)]

    d = lambda x: f"{x.day}.{x.month}.{x.year}"  # noqa: E731
    lines = [
        "Provizní sestava",
        f"Období: {d(spec.start)} - {d(spec.end)}",
        spec.holder,
        "Shrnutí",
        f"Provize za běžné období {czk(spec.regular)}",
        f"Mimořádné provize {czk(spec.extraordinary)}",
        f"Provize celkem {czk(spec.total)}",
        f"Uvolněno ze stornofondu {czk(spec.released)}",
        f"Odvedeno do stornofondu {czk(spec.paid_to_reserve)}",
        f"K výplatě {czk(payout)}",
        "Provize",
        "Počet Kč /",
        "Klient Smlouva Produkt Partner Základ Typ bodů bod Provize Poznámka",
    ]
    for client, contract, product, partner, amount in spec.rows:
        # A wrapped product name, as in real statements.
        lines.append("Pojištění -")
        points = f"{amount / 100:.1f}".replace(".", ",")
        lines.append(f"{client} {contract} {product} {partner} 12345 Z {points} 100 {czk(amount)}")
    lines += [
        f"Celkem 0,0 {czk(spec.commissions)}",
        "Meziprovize",
        "Finanční poradce Body Provize",
        f"Celkem 0,0 {czk(spec.inter_commissions)}",
        "Holdingové provize",
        "Klient Smlouva Provizní základ Provize v % Provize v Kč",
        f"Celkem {czk(spec.holding)}",
        "Mimořádné provize",
        "Popis Provize",
        f"Celkem {czk(spec.extraordinary)}",
        "Exekuce a srážky",
        "Popis Provize",
        f"Celkem {czk(spec.deductions)}",
        "Stornofond",
        "Minulé období Aktuálně Změna",
        "Nezasloužená provize 0 Kč 0 Kč 0 Kč",
        "Stornofond NP 1 000 Kč 1 200 Kč 200 Kč",
        "Stornofond celkem 1 000 Kč 1 200 Kč 200 Kč",
        "Aktuální výše stornofondu 1 200 Kč je v pořádku.",
        "Rozdělení příjmů pro uplatnění paušálních výdajů dle § 7 odst. 7 zákona o daních z příjmů",
        "Druh činnosti Provize",
    ]
    for heading, items, amount in activities:
        lines.append(heading if items else f"{heading} {czk(amount)}")
        for i, item in enumerate(items):
            # The amount sits on the second bullet line, like in real files.
            suffix = f" {czk(amount)}" if i == min(1, len(items) - 1) else ""
            lines.append(f"• {item}{suffix}")
    return "\n".join(lines)


def find_font() -> Path | None:
    """A TTF font with Czech glyphs, or None (then PDF tests are skipped)."""
    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    ]
    return next((p for p in candidates if p.is_file()), None)


def make_pdf(path: Path, text: str, font: Path) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(TTFont("TestFont", str(font)))
    pdf = canvas.Canvas(str(path), pagesize=A4)
    _, height = A4
    y = height - 40
    for line in text.splitlines():
        if y < 40:  # continue on a new page, like a long real statement
            pdf.showPage()
            y = height - 40
        pdf.setFont("TestFont", 8)
        pdf.drawString(30, y, line)
        y -= 11
    pdf.save()
    return path
