"""Findings produced by validation and aggregation.

Why issues are *codes + parameters* rather than ready-made sentences: the core
must stay Qt-free, yet the GUI shows messages in Czech or English and can switch
language at runtime. The core therefore only says *what* happened
(``IssueCode.GAP`` with ``{"start": ..., "end": ...}``); each front-end decides
*how* to phrase it. ``Issue.message()`` provides the English text for the CLI,
the GUI uses translatable templates in ``gui/issue_texts.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(int, Enum):
    # int-based so issues can be sorted / compared by severity.
    INFO = 0
    WARNING = 1
    ERROR = 2


class IssueCode(str, Enum):
    PARSE_FAILED = "parse_failed"
    TOTAL_MISMATCH = "total_mismatch"
    REGULAR_MISMATCH = "regular_mismatch"
    EXTRAORDINARY_MISMATCH = "extraordinary_mismatch"
    ACTIVITY_MISMATCH = "activity_mismatch"
    PAYOUT_MISMATCH = "payout_mismatch"
    DUPLICATE = "duplicate"
    CONFLICTING_DUPLICATE = "conflicting_duplicate"
    OVERLAP = "overlap"
    GAP = "gap"
    PARTIAL_COVERAGE = "partial_coverage"
    YEAR_BOUNDARY = "year_boundary"
    MULTIPLE_HOLDERS = "multiple_holders"
    UNKNOWN_ACTIVITY = "unknown_activity"
    NO_RULES_FOR_YEAR = "no_rules_for_year"


# English templates used by the CLI and as a fallback. Placeholders refer to
# keys of ``Issue.params``.
EN_TEMPLATES: dict[IssueCode, str] = {
    IssueCode.PARSE_FAILED: "Could not read the statement: {reason}",
    IssueCode.TOTAL_MISMATCH: (
        "'Provize celkem' ({total}) does not equal regular + extraordinary ({expected})."
    ),
    IssueCode.REGULAR_MISMATCH: (
        "'Provize za běžné období' ({regular}) does not match the detail tables ({expected})."
    ),
    IssueCode.EXTRAORDINARY_MISMATCH: (
        "Extraordinary commissions in the summary ({summary}) and in the table ({table}) differ."
    ),
    IssueCode.ACTIVITY_MISMATCH: (
        "Income split by activity ({activities}) does not equal 'Provize celkem' ({total})."
    ),
    IssueCode.PAYOUT_MISMATCH: (
        "Payout ({payout}) differs from the expected value ({expected}); this does not affect the tax base."
    ),
    IssueCode.DUPLICATE: "Duplicate of {original} (same period) - counted only once.",
    IssueCode.CONFLICTING_DUPLICATE: (
        "Same period as {original}, but with a different amount ({amount} vs {original_amount}). "
        "Only {original} is counted - remove the wrong file."
    ),
    IssueCode.OVERLAP: "Period overlaps with {other}.",
    IssueCode.GAP: "No statement for {start} – {end}; counted as zero commission.",
    IssueCode.PARTIAL_COVERAGE: "Loaded statements for {year} only cover {first} – {last}.",
    IssueCode.YEAR_BOUNDARY: (
        "Period ends on 31 December, so it is paid out in January {next_year}. "
        "Counted in {year} (mode: {mode})."
    ),
    IssueCode.MULTIPLE_HOLDERS: "Statements belong to more than one person: {holders}.",
    IssueCode.UNKNOWN_ACTIVITY: (
        "Unknown activity type '{category}' ({amount}) - choose its flat-rate percentage."
    ),
    IssueCode.NO_RULES_FOR_YEAR: (
        "No flat-rate rules for {year}; using rules for {used_year}. Check for an update."
    ),
}


@dataclass(frozen=True)
class Issue:
    code: IssueCode
    severity: Severity
    source: Path | None = None
    params: dict[str, Any] = field(default_factory=dict, hash=False)

    def message(self) -> str:
        return EN_TEMPLATES[self.code].format(**{k: str(v) for k, v in self.params.items()})
