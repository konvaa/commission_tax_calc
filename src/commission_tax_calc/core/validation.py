"""Internal consistency checks of a single statement.

The PDF prints every amount rounded to whole crowns, while the underlying
values have decimals (e.g. 6.6 points x 112.5 CZK = 742.5, printed as 741 -
the points are rounded too). Sums of rounded numbers can therefore differ from
the rounded total by up to 1 CZK per term. The tolerance below is derived from
the number of terms instead of a magic constant, so a real misread (hundreds or
thousands of CZK) is still caught.
"""

from __future__ import annotations

from decimal import Decimal

from .issues import Issue, IssueCode, Severity
from .models import Statement
from .money import format_czk

_PER_TERM = Decimal("1")


def _close(a: Decimal, b: Decimal, terms: int) -> bool:
    return abs(a - b) <= _PER_TERM * terms


def validate_statement(st: Statement) -> list[Issue]:
    s, t = st.summary, st.sections
    issues: list[Issue] = []

    def add(code: IssueCode, severity: Severity, **params) -> None:
        issues.append(Issue(code, severity, st.source, params))

    expected_total = s.regular + s.extraordinary
    if not _close(s.total, expected_total, 2):
        add(
            IssueCode.TOTAL_MISMATCH,
            Severity.WARNING,
            total=format_czk(s.total),
            expected=format_czk(expected_total),
        )

    expected_regular = t.commissions + t.inter_commissions + t.holding
    if not _close(s.regular, expected_regular, 3):
        add(
            IssueCode.REGULAR_MISMATCH,
            Severity.WARNING,
            regular=format_czk(s.regular),
            expected=format_czk(expected_regular),
        )

    if not _close(s.extraordinary, t.extraordinary, 1):
        add(
            IssueCode.EXTRAORDINARY_MISMATCH,
            Severity.WARNING,
            summary=format_czk(s.extraordinary),
            table=format_czk(t.extraordinary),
        )

    # This is the check that matters most for the tax return: the per-activity
    # split is what gets multiplied by the flat-rate percentages.
    activities_sum = sum((a.amount for a in st.activities), Decimal(0))
    if not _close(activities_sum, s.total, len(st.activities)):
        add(
            IssueCode.ACTIVITY_MISMATCH,
            Severity.WARNING,
            activities=format_czk(activities_sum),
            total=format_czk(s.total),
        )

    # Payout = commission + released reserve + (negative) contribution to the
    # reserve - deductions. The sign of deductions in the PDF is not known from
    # the samples, so abs() makes the check independent of it. Only INFO,
    # because the payout is not part of the tax base.
    expected_payout = s.total + s.released_from_reserve + s.paid_to_reserve - abs(t.deductions)
    if not _close(s.payout, expected_payout, 3):
        add(
            IssueCode.PAYOUT_MISMATCH,
            Severity.INFO,
            payout=format_czk(s.payout, 2),
            expected=format_czk(expected_payout, 2),
        )
    return issues
