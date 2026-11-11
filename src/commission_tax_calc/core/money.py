"""Parsing and formatting of Czech currency amounts.

Why ``Decimal`` and not ``float``: binary floats cannot represent most decimal
fractions exactly (``0.1 + 0.2 != 0.3``). Summing two dozen statements with
floats could drift by a fraction of a crown, which is unacceptable for a tax
return. ``Decimal`` keeps the exact value that is printed in the PDF.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Thousands separators seen in Czech documents: normal space, no-break space
# and narrow no-break space (the latter two are common in PDF generators).
_SPACES = "   "

# One amount, e.g. "741", "-4 418", "1 128,47". The look-behind ``(?<!\S)``
# guarantees the number starts at a word boundary. Without it, a line such as
# "6,6 112.5 741 Kč" would match "5 741" (the "5" of "112.5" glued to "741").
AMOUNT_PATTERN = r"(?<!\S)[-−]?\d{1,3}(?:[   ]\d{3})*(?:,\d{1,2})?"

# An amount followed by the currency, anchored at the end of a line.
_TRAILING_CZK = re.compile(rf"({AMOUNT_PATTERN})\s*Kč\s*$")


class AmountError(ValueError):
    """Raised when a string cannot be interpreted as a CZK amount."""


def parse_czk(text: str) -> Decimal:
    """Convert ``"1 128,47 Kč"`` / ``"-4 418"`` to ``Decimal``."""
    cleaned = text.strip()
    if cleaned.endswith("Kč"):
        cleaned = cleaned[:-2]
    for ch in _SPACES:
        cleaned = cleaned.replace(ch, "")
    # Typographic minus (U+2212) occasionally replaces the ASCII hyphen.
    cleaned = cleaned.replace("−", "-").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise AmountError(f"Not a CZK amount: {text!r}") from exc


def trailing_czk(line: str) -> tuple[str, Decimal] | None:
    """Split ``"Provize celkem 741 Kč"`` into ``("Provize celkem", Decimal(741))``.

    Returns ``None`` when the line does not end with an amount in CZK.
    """
    match = _TRAILING_CZK.search(line)
    if match is None:
        return None
    return line[: match.start()].rstrip(), parse_czk(match.group(1))


def format_czk(value: Decimal, decimals: int = 0) -> str:
    """Format a value the Czech way: ``Decimal("1128.47") -> "1 128,47 Kč"``.

    Formatting is done manually instead of via the ``locale`` module because
    ``locale`` depends on what is installed on the OS (and is process-global),
    which makes output differ between a developer PC, CI and the .exe build.
    """
    quantum = Decimal(1).scaleb(-decimals)
    rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
    sign = "-" if rounded < 0 else ""
    integer, _, fraction = f"{abs(rounded):f}".partition(".")
    groups = []
    while integer:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    text = " ".join(groups) or "0"
    if decimals:
        text += "," + fraction.ljust(decimals, "0")
    return f"{sign}{text} Kč"
