"""Translatable texts for core issue codes.

Each template is spelled out as a literal ``QCoreApplication.translate`` call.
That looks repetitive, but ``pyside6-lupdate`` only extracts *literal*
strings - a loop over ``EN_TEMPLATES`` would compile fine and silently never
be translated. A unit test checks that every ``IssueCode`` is covered here.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication

from ..core.issues import Issue, IssueCode, Severity


def _templates() -> dict[IssueCode, str]:
    return {
        IssueCode.PARSE_FAILED: QCoreApplication.translate(
            "Issues", "Could not read the statement: {reason}"
        ),
        IssueCode.TOTAL_MISMATCH: QCoreApplication.translate(
            "Issues",
            "'Provize celkem' ({total}) does not equal regular + extraordinary ({expected}).",
        ),
        IssueCode.REGULAR_MISMATCH: QCoreApplication.translate(
            "Issues",
            "'Provize za běžné období' ({regular}) does not match the detail tables ({expected}).",
        ),
        IssueCode.EXTRAORDINARY_MISMATCH: QCoreApplication.translate(
            "Issues",
            "Extraordinary commissions in the summary ({summary}) and in the table ({table}) differ.",
        ),
        IssueCode.ACTIVITY_MISMATCH: QCoreApplication.translate(
            "Issues",
            "Income split by activity ({activities}) does not equal 'Provize celkem' ({total}).",
        ),
        IssueCode.PAYOUT_MISMATCH: QCoreApplication.translate(
            "Issues",
            "Payout ({payout}) differs from the expected value ({expected}); "
            "this does not affect the tax base.",
        ),
        IssueCode.DUPLICATE: QCoreApplication.translate(
            "Issues", "Duplicate of {original} (same period) - counted only once."
        ),
        IssueCode.CONFLICTING_DUPLICATE: QCoreApplication.translate(
            "Issues",
            "Same period as {original}, but with a different amount ({amount} vs "
            "{original_amount}). Only {original} is counted - remove the wrong file.",
        ),
        IssueCode.OVERLAP: QCoreApplication.translate("Issues", "Period overlaps with {other}."),
        IssueCode.GAP: QCoreApplication.translate(
            "Issues", "No statement for {start} – {end}; counted as zero commission."
        ),
        IssueCode.PARTIAL_COVERAGE: QCoreApplication.translate(
            "Issues", "Loaded statements for {year} only cover {first} – {last}."
        ),
        IssueCode.YEAR_BOUNDARY: QCoreApplication.translate(
            "Issues",
            "Period ends on 31 December, so it is paid out in January {next_year}. "
            "Counted in {year} (mode: {mode}).",
        ),
        IssueCode.MULTIPLE_HOLDERS: QCoreApplication.translate(
            "Issues", "Statements belong to more than one person: {holders}."
        ),
        IssueCode.UNKNOWN_ACTIVITY: QCoreApplication.translate(
            "Issues",
            "Unknown activity type '{category}' ({amount}) - choose its flat-rate percentage.",
        ),
        IssueCode.NO_RULES_FOR_YEAR: QCoreApplication.translate(
            "Issues",
            "No flat-rate rules for {year}; using rules for {used_year}. Check for an update.",
        ),
        IssueCode.UNKNOWN_DOCUMENT: QCoreApplication.translate(
            "Issues", "Not recognized as a commission statement or an invoice."
        ),
        IssueCode.OCR_UNAVAILABLE: QCoreApplication.translate(
            "Issues", "Scanned document, but OCR is not available ({reason}). Enter the values by hand."
        ),
        IssueCode.MY_ICO_UNKNOWN: QCoreApplication.translate(
            "Issues", "Your IČO is not set - all invoices are treated as issued by you."
        ),
        IssueCode.INVOICE_RECEIVED: QCoreApplication.translate(
            "Issues", "Invoice {number} was issued to you by {supplier} - not counted."
        ),
        IssueCode.INVOICE_NEEDS_REVIEW: QCoreApplication.translate(
            "Issues", "Invoice {number} was read from {origin} - check and confirm its values."
        ),
        IssueCode.INVOICE_ADVANCE: QCoreApplication.translate(
            "Issues", "Advance document {number} - not counted (the final invoice is counted)."
        ),
        IssueCode.INVOICE_DUPLICATE: QCoreApplication.translate(
            "Issues", "Duplicate of {original} - counted only once."
        ),
        IssueCode.INVOICE_CONFLICT: QCoreApplication.translate(
            "Issues",
            "Invoice number {number} appears twice with different amounts ({amount} vs {other_amount}).",
        ),
        IssueCode.INVOICE_NO_AMOUNT: QCoreApplication.translate(
            "Issues", "Invoice {number}: the amount could not be read - not counted until confirmed."
        ),
        IssueCode.INVOICE_NO_DATE: QCoreApplication.translate(
            "Issues", "Invoice {number}: no date found - the tax year cannot be determined."
        ),
        IssueCode.INVOICE_PAYMENT_UNCONFIRMED: QCoreApplication.translate(
            "Issues",
            "Invoice {number} was issued in {issue_year}, but its due date {due} falls in {year}. "
            "Confirm the actual payment date.",
        ),
        IssueCode.INVOICE_NUMBER_GAP: QCoreApplication.translate(
            "Issues", "Invoice number(s) {missing} missing in the sequence."
        ),
        IssueCode.INVOICES_UNASSIGNED: QCoreApplication.translate(
            "Issues", "{count} invoice(s) without a flat-rate category ({amount})."
        ),
        IssueCode.INVOICES_AUTO_ASSIGNED: QCoreApplication.translate(
            "Issues",
            "{count} invoice(s) got their rate automatically from a remembered group - please check.",
        ),
    }


def mode_label(mode_value: str) -> str:
    if mode_value == "payout":
        return QCoreApplication.translate("Issues", "by payout")
    return QCoreApplication.translate("Issues", "by period")


def origin_label(origin: str) -> str:
    if origin == "ocr":
        return QCoreApplication.translate("Issues", "a scan (OCR)")
    return QCoreApplication.translate("Issues", "the PDF text")


def issue_text(issue: Issue) -> str:
    params = {k: str(v) for k, v in issue.params.items()}
    if "mode" in params:
        params["mode"] = mode_label(params["mode"])
    if "origin" in params:
        params["origin"] = origin_label(params["origin"])
    template = _templates().get(issue.code)
    if template is None:
        return issue.message()
    try:
        return template.format(**params)
    except (KeyError, IndexError):
        # A translator broke a placeholder - fall back to English, never crash.
        return issue.message()


def severity_text(severity: Severity) -> str:
    return {
        Severity.INFO: QCoreApplication.translate("Issues", "Info"),
        Severity.WARNING: QCoreApplication.translate("Issues", "Warning"),
        Severity.ERROR: QCoreApplication.translate("Issues", "Error"),
    }[severity]
