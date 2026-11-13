"""Czech company ID (IČO) validation.

The 8th digit of an IČO is a mod-11 checksum of the first seven. Checking it
catches most OCR misreads (a "3" read as "8") before a wrong IČO is used to
decide whether an invoice is ours or is sent to ARES.
"""

from __future__ import annotations

import re

_WEIGHTS = (8, 7, 6, 5, 4, 3, 2)


def normalize(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\s", "", value)
    if not digits.isdigit() or len(digits) > 8:
        return None
    return digits.zfill(8)  # older IČOs are sometimes written without leading zeros


def is_valid(value: str | None) -> bool:
    ico = normalize(value)
    if ico is None:
        return False
    total = sum(int(d) * w for d, w in zip(ico[:7], _WEIGHTS, strict=True))
    return (11 - total % 11) % 10 == int(ico[7])
