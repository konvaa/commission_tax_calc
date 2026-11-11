from decimal import Decimal

from commission_tax_calc.core.issues import IssueCode, Severity
from commission_tax_calc.core.validation import validate_statement


def codes(issues):
    return {i.code for i in issues}


def test_consistent_statement_has_no_issues(statement):
    assert validate_statement(statement(paid_to_reserve=-150, released=20)) == []


def test_rounding_within_tolerance_is_ok(statement):
    # Real case: 741 + 388 = 1129, but the PDF says 1128.47 (rounded inputs).
    st = statement(rows=[("A", "1", "P", "X, a.s.", 741)], released=388, payout=Decimal("1128.47"))
    assert validate_statement(st) == []


def test_total_mismatch(statement):
    st = statement(total_override=5000, activities=[("Není živností", (), 5000)])
    assert IssueCode.TOTAL_MISMATCH in codes(validate_statement(st))


def test_activity_split_mismatch(statement):
    st = statement(activities=[("Není živností", (), 400)])
    issues = validate_statement(st)
    assert codes(issues) == {IssueCode.ACTIVITY_MISMATCH}
    assert issues[0].severity is Severity.WARNING


def test_payout_mismatch_is_only_info(statement):
    issues = validate_statement(statement(payout=Decimal(10)))
    assert codes(issues) == {IssueCode.PAYOUT_MISMATCH}
    assert issues[0].severity is Severity.INFO
