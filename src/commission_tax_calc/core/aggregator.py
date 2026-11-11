"""Yearly aggregation: tax-year assignment, duplicates, gaps and totals."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

from .issues import Issue, IssueCode, Severity
from .models import Period, Statement
from .money import format_czk
from .validation import validate_statement


class YearMode(str, Enum):
    """How a statement is assigned to a tax year.

    The PDF contains the period but not the payout date, so the payout date can
    only be approximated:

    * ``BY_PERIOD`` - the year of the period (accrual view). Default.
    * ``BY_PAYOUT`` - cash view: a statement is paid shortly after its period
      ends, so a period ending on 31 December is paid in January and counts
      towards the next year.

    Which one applies to you is a tax question; the app makes the choice
    explicit instead of hiding it.
    """

    BY_PERIOD = "period"
    BY_PAYOUT = "payout"


def tax_year_of(period: Period, mode: YearMode) -> int:
    if mode is YearMode.BY_PAYOUT and (period.end.month, period.end.day) == (12, 31):
        return period.end.year + 1
    return period.end.year


@dataclass(frozen=True)
class StatementRow:
    """A statement as shown in the overview, with its status for the year."""

    statement: Statement
    tax_year: int
    counted: bool  # False for duplicates
    issues: tuple[Issue, ...]

    @property
    def severity(self) -> Severity:
        return max((i.severity for i in self.issues), default=Severity.INFO)


@dataclass
class YearReport:
    year: int
    mode: YearMode
    rows: list[StatementRow] = field(default_factory=list)
    activity_totals: dict[str, Decimal] = field(default_factory=dict)
    total: Decimal = Decimal(0)
    payout_total: Decimal = Decimal(0)
    issues: list[Issue] = field(default_factory=list)  # year-level findings

    @property
    def counted(self) -> list[Statement]:
        return [r.statement for r in self.rows if r.counted]

    def all_issues(self) -> list[Issue]:
        per_row = [i for r in self.rows for i in r.issues]
        return sorted(self.issues + per_row, key=lambda i: -i.severity)


def available_years(statements: list[Statement], mode: YearMode) -> list[int]:
    return sorted({tax_year_of(s.period, mode) for s in statements})


def deduplicate(statements: list[Statement]) -> tuple[list[Statement], dict[int, Issue]]:
    """Keep the first statement per period; return issues keyed by ``id()``.

    Two files for the same period are either a re-download (same amount) or a
    corrected statement (different amount). The first is harmless and only
    INFO; the second is an ERROR because the app cannot know which is right.
    """
    by_period: dict[Period, Statement] = {}
    issues: dict[int, Issue] = {}
    for st in sorted(statements, key=_original_first):
        original = by_period.get(st.period)
        if original is None:
            by_period[st.period] = st
            continue
        if original.summary.total == st.summary.total:
            issues[id(st)] = Issue(
                IssueCode.DUPLICATE, Severity.INFO, st.source, {"original": original.source.name}
            )
        else:
            issues[id(st)] = Issue(
                IssueCode.CONFLICTING_DUPLICATE,
                Severity.ERROR,
                st.source,
                {
                    "original": original.source.name,
                    "amount": format_czk(st.summary.total),
                    "original_amount": format_czk(original.summary.total),
                },
            )
    return list(by_period.values()), issues


_COPY_SUFFIX = re.compile(r"(\s*\(\d+\)|\s*-\s*(kopie|copy))$", re.IGNORECASE)


def _original_first(st: Statement) -> tuple[bool, str]:
    """Sort key preferring "x.pdf" over browser re-downloads like "x (1).pdf".

    A plain name sort would pick "x (1).pdf" first (space sorts before dot)
    and flag the original as the duplicate, which is confusing.
    """
    stem = st.source.stem
    return bool(_COPY_SUFFIX.search(stem)), str(st.source).casefold()


def find_gaps(periods: list[Period]) -> list[Period]:
    """Return the uncovered ranges between consecutive (sorted) periods."""
    gaps = []
    ordered = sorted(set(periods))
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current.start > previous.next_day():
            gaps.append(Period(previous.next_day(), current.start - timedelta(days=1)))
    return gaps


def build_report(statements: list[Statement], year: int, mode: YearMode) -> YearReport:
    report = YearReport(year=year, mode=mode)
    unique, dup_issues = deduplicate(statements)
    unique_ids = {id(s) for s in unique}

    for st in sorted(statements, key=lambda s: (s.period, str(s.source))):
        st_year = tax_year_of(st.period, mode)
        if st_year != year:
            continue
        issues = list(validate_statement(st))
        if id(st) in dup_issues:
            issues.append(dup_issues[id(st)])
        if (st.period.end.month, st.period.end.day) == (12, 31):
            issues.append(
                Issue(
                    IssueCode.YEAR_BOUNDARY,
                    Severity.INFO,
                    st.source,
                    {"next_year": st.period.end.year + 1, "year": st_year, "mode": mode.value},
                )
            )
        report.rows.append(StatementRow(st, st_year, id(st) in unique_ids, tuple(issues)))

    counted = report.counted
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for st in counted:
        report.total += st.summary.total
        report.payout_total += st.summary.payout
        for activity in st.activities:
            totals[activity.category] += activity.amount
    report.activity_totals = dict(totals)

    report.issues.extend(_overlap_issues(counted))
    report.issues.extend(_coverage_issues(unique, counted, year, mode))

    holders = sorted({s.holder for s in statements if s.holder})
    if len(holders) > 1:
        report.issues.append(
            Issue(IssueCode.MULTIPLE_HOLDERS, Severity.WARNING, None, {"holders": ", ".join(holders)})
        )
    return report


def _overlap_issues(counted: list[Statement]) -> list[Issue]:
    issues = []
    ordered = sorted(counted, key=lambda s: s.period)
    for a, b in zip(ordered, ordered[1:], strict=False):
        if a.period.overlaps(b.period):
            issues.append(Issue(IssueCode.OVERLAP, Severity.WARNING, b.source, {"other": a.source.name}))
    return issues


def _coverage_issues(
    all_unique: list[Statement], counted: list[Statement], year: int, mode: YearMode
) -> list[Issue]:
    if not counted:
        return []
    first = min(s.period.start for s in counted)
    last = max(s.period.end for s in counted)
    issues = []

    # Gaps are computed over *all* loaded periods, then limited to this year's
    # span - otherwise a gap right at the boundary of two years would be missed.
    # Only INFO: FinTrust issues no statement for a period with zero commission,
    # so a gap is normally fine. It is still listed, so a statement that was
    # simply not downloaded can be spotted.
    for gap in find_gaps([s.period for s in all_unique]):
        if gap.start <= last and gap.end >= first:
            issues.append(
                Issue(
                    IssueCode.GAP,
                    Severity.INFO,
                    None,
                    {"start": _cz(gap.start), "end": _cz(gap.end)},
                )
            )

    if mode is YearMode.BY_PERIOD:
        expected_first, expected_last = date(year, 1, 1), date(year, 12, 31)
        complete = first <= expected_first and last >= expected_last
    else:
        # Cash view: the year starts with the statement that ended on 31.12. of
        # the previous year and ends before the one ending on 31.12. this year.
        complete = (
            any(s.period.end == date(year - 1, 12, 31) for s in counted)
            and last.month == 12
            and last.year == year
        )
    if not complete:
        issues.append(
            Issue(
                IssueCode.PARTIAL_COVERAGE,
                Severity.INFO,
                None,
                {"year": year, "first": _cz(first), "last": _cz(last)},
            )
        )
    return issues


def _cz(d: date) -> str:
    return f"{d.day}.{d.month}.{d.year}"
