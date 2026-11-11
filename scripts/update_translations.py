"""Refresh translation files after changing UI texts.

    python scripts/update_translations.py

1. ``pyside6-lupdate`` scans gui/*.py and updates translations/app_cs.ts:
   new strings are added as "unfinished", removed ones marked "vanished",
   existing translations are kept.
2. Translate the new strings in Qt Linguist (``pyside6-linguist``) or by hand.
3. Run this script again: ``pyside6-lrelease`` compiles the .ts into the .qm
   file that the app loads at runtime.

The .qm file is committed too, so the app works straight from a git checkout
without needing the Qt tools installed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "commission_tax_calc"
LANGUAGES = ["cs"]


def main() -> int:
    sources = sorted(str(p) for p in (PACKAGE / "gui").glob("*.py"))
    for lang in LANGUAGES:
        ts = PACKAGE / "translations" / f"app_{lang}.ts"
        qm = ts.with_suffix(".qm")
        subprocess.run(["pyside6-lupdate", *sources, "-ts", str(ts)], check=True)
        subprocess.run(["pyside6-lrelease", str(ts), "-qm", str(qm)], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
