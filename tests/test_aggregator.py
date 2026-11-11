from datetime import date
from decimal import Decimal

from commission_tax_calc.core.aggregator import (
    YearMode,
    available_years,
    build_report,
    find_gaps,
    tax_year_of,
)
from commission_tax_calc.core.issues import IssueCode, Severity
from commission_tax_calc.core.models import Period


def year_of_statements(statement, year=2030, amount=1000):
    """24 half-month statements covering the whole year."""
    result = []
    for month in range(1, 13):
        last = (date(year, month % 12 + 1, 1) if month < 12 else date(year + 1, 1, 1)).toordinal() - 1
        halves = [
            (date(year, month, 1), date(year, month, 14)),
            (date(year, month, 15), date.fromordinal(last)),
        ]
        for start, end in halves:
            result.append(
                statement(
                    f"{start.isoformat()}.pdf",
                    start=start,
                    end=end,
                    rows=[("A", "1", "P", "X, a.s.", amount)],
                )
            )
    return result


def year_codes(report):
    return [i.code for i in report.issues]


def test_full_year_sums_and_has_no_warnings(statement):
    report = build_report(year_of_statements(statement), 2030, YearMode.BY_PERIOD)
    assert report.total == Decimal(24000)
    assert len(report.counted) == 24
    assert report.activity_totals == {"Není živností, řídí se zvláštním předpisem": Decimal(24000)}
    assert all(i.severity is Severity.INFO for i in report.all_issues())
    assert IssueCode.PARTIAL_COVERAGE not in year_codes(report)


def test_gap_is_reported(statement):
    statements = year_of_statements(statement)
    del statements[21]  # 15.-30. November
    report = build_report(statements, 2030, YearMode.BY_PERIOD)
    gaps = [i for i in report.issues if i.code is IssueCode.GAP]
    assert len(gaps) == 1
    assert gaps[0].params == {"start": "15.11.2030", "end": "30.11.2030"}
    # No statement = zero commission at FinTrust, so a gap is not a warning.
    assert gaps[0].severity is Severity.INFO
    assert report.total == Decimal(23000)


def test_identical_duplicate_counted_once(statement):
    a = statement("a.pdf")
    b = statement("b (1).pdf")
    report = build_report([b, a], 2030, YearMode.BY_PERIOD)
    assert report.total == Decimal(1000)
    duplicate_row = next(r for r in report.rows if not r.counted)
    assert duplicate_row.statement.source.name == "b (1).pdf"
    assert IssueCode.DUPLICATE in {i.code for i in duplicate_row.issues}
    assert duplicate_row.severity is Severity.INFO


def test_original_preferred_over_browser_copy(statement):
    original = statement("sestava.pdf")
    copy = statement("sestava (1).pdf")
    report = build_report([original, copy], 2030, YearMode.BY_PERIOD)
    counted = [r.statement.source.name for r in report.rows if r.counted]
    assert counted == ["sestava.pdf"]


def test_conflicting_duplicate_is_an_error(statement):
    a = statement("a.pdf")
    b = statement("b.pdf", rows=[("A", "1", "P", "X, a.s.", 9999)])
    report = build_report([a, b], 2030, YearMode.BY_PERIOD)
    assert report.total == Decimal(1000)  # first by name is kept
    issue = next(i for i in report.all_issues() if i.code is IssueCode.CONFLICTING_DUPLICATE)
    assert issue.severity is Severity.ERROR


def test_overlap_warning(statement):
    a = statement("a.pdf", start=date(2030, 1, 1), end=date(2030, 1, 14))
    b = statement("b.pdf", start=date(2030, 1, 10), end=date(2030, 1, 31))
    report = build_report([a, b], 2030, YearMode.BY_PERIOD)
    assert IssueCode.OVERLAP in year_codes(report)


def test_year_modes():
    december = Period(date(2030, 12, 15), date(2030, 12, 31))
    early_december = Period(date(2030, 12, 1), date(2030, 12, 14))
    assert tax_year_of(december, YearMode.BY_PERIOD) == 2030
    assert tax_year_of(december, YearMode.BY_PAYOUT) == 2031
    assert tax_year_of(early_december, YearMode.BY_PAYOUT) == 2030


def test_payout_mode_moves_late_december(statement):
    st = statement(start=date(2030, 12, 15), end=date(2030, 12, 31))
    assert available_years([st], YearMode.BY_PAYOUT) == [2031]
    report = build_report([st], 2031, YearMode.BY_PAYOUT)
    assert report.total == Decimal(1000)
    assert IssueCode.YEAR_BOUNDARY in {i.code for i in report.rows[0].issues}


def test_partial_coverage_info(statement):
    report = build_report(
        [statement(start=date(2030, 10, 15), end=date(2030, 10, 31))], 2030, YearMode.BY_PERIOD
    )
    issue = next(i for i in report.issues if i.code is IssueCode.PARTIAL_COVERAGE)
    assert issue.params["first"] == "15.10.2030"


def test_multiple_holders_warning(statement):
    a = statement("a.pdf")
    b = statement("b.pdf", holder="Jiný Člověk", start=date(2030, 1, 15), end=date(2030, 1, 31))
    report = build_report([a, b], 2030, YearMode.BY_PERIOD)
    assert IssueCode.MULTIPLE_HOLDERS in year_codes(report)


def test_find_gaps_ignores_adjacent_periods():
    periods = [
        Period(date(2030, 1, 1), date(2030, 1, 14)),
        Period(date(2030, 1, 15), date(2030, 1, 31)),
        Period(date(2030, 3, 1), date(2030, 3, 14)),
    ]
    assert find_gaps(periods) == [Period(date(2030, 2, 1), date(2030, 2, 28))]
