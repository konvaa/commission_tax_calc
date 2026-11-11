"""Generate a folder of fictitious statements to try the app without real data.

    pip install reportlab
    python scripts/make_demo_statements.py demo_statements

The demo year deliberately contains the situations the app should catch:
a missing half-month, a re-downloaded duplicate and a late-December statement.
All names and numbers are invented.
"""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from factory import Spec, find_font, make_pdf, make_text  # noqa: E402

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
    print(f"Demo statements written to {out.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))
