"""Generate a folder of fictitious documents to try the app without real data.

    pip install reportlab
    python scripts/make_demo_data.py demo_data

Commission statements: a missing half-month, a re-downloaded duplicate and a
late-December statement. Invoices: two kinds of work for two customers (so the
grouping has something to do), a credit note, an invoice without ISDOC (read
from the PDF text) and a scanned invoice (read by OCR).
All names, IČOs and numbers are invented.
"""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from factory import (  # noqa: E402
    CUSTOMER_A,
    CUSTOMER_B,
    InvoiceSpec,
    Spec,
    find_font,
    make_invoice_pdf,
    make_pdf,
    make_scanned_pdf,
    make_text,
)

CLIENTS = ["Nováková Eva", "Svoboda Karel", "Dvořák Pavel", "Černá Lucie", "Procházka Jan"]
PRODUCTS = [
    ("Rizikové životní pojištění", "Smyšlená pojišťovna, a.s."),
    ("Pojištění domácnosti", "Vymyšlená pojišťovna, a.s."),
    ("Doplňkové penzijní spoření", "Fiktivní penzijní společnost, a.s."),
]


def half_months(year: int):
    for month in range(1, 13):
        first = date(year, month, 1)
        last = (date(year + (month == 12), month % 12 + 1, 1)) - timedelta(days=1)
        yield first, date(year, month, 14)
        yield date(year, month, 15), last


def main(target: str = "demo_statements", year: int = 2025) -> int:
    font = find_font()
    if font is None:
        print("No TTF font with Czech glyphs found.", file=sys.stderr)
        return 1
    out = Path(target)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)  # deterministic demo data
    for start, end in half_months(year):
        if (start.month, start.day) == (11, 15):
            continue  # a missing statement - the app reports the gap
        rows = []
        for _ in range(rng.randint(1, 3)):
            product, partner = rng.choice(PRODUCTS)
            rows.append(
                (
                    rng.choice(CLIENTS),
                    str(rng.randint(10**9, 10**10)),
                    product,
                    partner,
                    rng.randint(3, 400) * 10,
                )
            )
        commission = sum(r[4] for r in rows)
        paid = -round(commission * 0.15)
        released = rng.choice([0, 0, rng.randint(1, 50) * 10])
        spec = Spec(
            start=start,
            end=end,
            holder="Ukázkový Poradce",
            rows=rows,
            paid_to_reserve=paid,
            released=released,
        )
        period = f"{start.day}-{start.month}-{year}-{end.day}-{end.month}-{year}"
        name = f"provizni-sestava-ukazka-obdobi-{period}.pdf"
        make_pdf(out / name, make_text(spec), font)
        if (start.month, start.day) == (3, 1):
            make_pdf(out / name.replace(".pdf", " (1).pdf"), make_text(spec), font)  # re-download
    make_demo_invoices(out, year, font, rng)
    print(f"Demo data written to {out.resolve()}")
    return 0


ELECTRICAL = ["Montáž elektroinstalace", "Revize elektroinstalace", "Výměna rozvaděče"]
DESIGN = ["Projektová dokumentace přípojky NN", "Projektová dokumentace rozvodů"]
PLACES = ["Lužná", "Doubrava", "Hlinka", "Nová Pláň", "Lhota", "Medlov", "Trojanovice", "Kunčice"]


def make_demo_invoices(out: Path, year: int, font: Path, rng: random.Random) -> None:
    number = 1
    for month in range(1, 13):
        kind, customer = (ELECTRICAL, CUSTOMER_A) if month % 3 else (DESIGN, CUSTOMER_B)
        issue = date(year, month, rng.randint(3, 25))
        spec = InvoiceSpec(
            number=f"{year}{number:04d}",
            supplier_name="Ukázkový Poradce",
            customer_ico=customer[0],
            customer_name=customer[1],
            issue=issue,
            due=issue + timedelta(days=14),
            lines=[
                (f"{rng.choice(kind)}, {rng.choice(PLACES)}", rng.randint(20, 160) * 100)
                for _ in range(rng.randint(1, 3))
            ],
        )
        name = f"faktura-{spec.number}.pdf"
        if month == 5:
            make_invoice_pdf(out / name, spec, font, embed_isdoc=False)  # no ISDOC -> text heuristics
        elif month == 8:
            make_scanned_pdf(out / name, spec, font)  # a scan -> OCR
        else:
            make_invoice_pdf(out / name, spec, font)
        number += 1
    credit = InvoiceSpec(
        number=f"{year}{number:04d}",
        supplier_name="Ukázkový Poradce",
        doc_type=2,
        issue=date(year, 11, 20),
        due=date(year, 11, 30),
        lines=[("Sleva za reklamaci, Lužná", 2500)],
    )
    make_invoice_pdf(out / f"dobropis-{credit.number}.pdf", credit, font)


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))
