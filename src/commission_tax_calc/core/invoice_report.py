"""Yearly evaluation of issued invoices.

Order of decisions for every invoice (each step explained where it happens):
1. apply the user's corrections, re-read text invoices with the known IČO,
2. keep only invoices issued by the user,
3. determine the payment date -> tax year (cash basis of "daňová evidence"),
4. skip duplicates and advance documents,
5. pick the flat-rate category: manual > remembered group > ARES > none.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .grouping import InvoiceGroup, best_profile, group_invoices
from .ico import is_valid
from .invoice_models import Invoice, Origin
from .invoice_store import InvoiceStore
from .invoice_text import parse_invoice_text
from .issues import Issue, IssueCode, Severity
from .money import format_czk


class RateSource:
    MANUAL = "manual"
    GROUP = "group"
    ARES = "ares"


@dataclass(frozen=True)
class InvoiceRow:
    invoice: Invoice
    payment_date: date | None
    payment_confirmed: bool
    tax_year: int | None
    counted: bool
    issued_by_me: bool
    rate_id: str | None
    rate_source: str | None
    issues: tuple[Issue, ...]
    group_id: str | None = None

    @property
    def severity(self) -> Severity | None:
        return max((i.severity for i in self.issues), default=None)


@dataclass
class InvoiceReport:
    year: int
    rows: list[InvoiceRow] = field(default_factory=list)
    groups: list[InvoiceGroup] = field(default_factory=list)
    rate_income: dict[str, Decimal] = field(default_factory=dict)
    unassigned: Decimal = Decimal(0)
    issues: list[Issue] = field(default_factory=list)

    @property
    def counted(self) -> list[InvoiceRow]:
        return [r for r in self.rows if r.counted]

    @property
    def total(self) -> Decimal:
        return sum(self.rate_income.values(), Decimal(0)) + self.unassigned

    def all_issues(self) -> list[Issue]:
        return sorted(self.issues + [i for r in self.rows for i in r.issues], key=lambda i: -i.severity)


def detect_my_ico(invoices: list[Invoice]) -> str | None:
    """The most frequent valid supplier IČO - a proposal the user confirms.

    Structured (ISDOC) invoices weigh more than OCR guesses.
    """
    votes: Counter[str] = Counter()
    for invoice in invoices:
        if invoice.supplier_ico and is_valid(invoice.supplier_ico):
            votes[invoice.supplier_ico] += 3 if invoice.origin is Origin.ISDOC else 1
    return votes.most_common(1)[0][0] if votes else None


def prepare(invoice: Invoice, store: InvoiceStore) -> Invoice:
    """Apply the user's corrections and re-read text invoices with own IČO."""
    if invoice.origin is not Origin.ISDOC and invoice.raw_text and invoice.key not in store.corrections:
        invoice = parse_invoice_text(
            invoice.raw_text, invoice.source, invoice.key, invoice.origin, store.my_ico, invoice.page_count
        ).with_changes(raw_text=invoice.raw_text)
    return store.apply(invoice)


def payment_date(invoice: Invoice, store: InvoiceStore) -> tuple[date | None, bool]:
    """Confirmed payment date, else the due date as the best estimate.

    Under "daňová evidence" income counts when the money arrives. The invoice
    does not say when that happened; the due date is the most likely day,
    and the user confirms it where it matters (see PAYMENT_UNCONFIRMED).
    """
    if invoice.key in store.payment_dates:
        return store.payment_dates[invoice.key], True
    return invoice.due_date or invoice.tax_point_date or invoice.issue_date, False


def invoice_years(invoices: list[Invoice], store: InvoiceStore) -> set[int]:
    years = set()
    for invoice in invoices:
        paid, _ = payment_date(prepare(invoice, store), store)
        if paid:
            years.add(paid.year)
    return years


def build_invoice_report(
    invoices: list[Invoice],
    year: int,
    store: InvoiceStore,
    ares_rate_ids: set[str] | None = None,
) -> InvoiceReport:
    report = InvoiceReport(year=year)
    my_ico = store.my_ico
    if invoices and not my_ico:
        report.issues.append(Issue(IssueCode.MY_ICO_UNKNOWN, Severity.WARNING))
    # ARES helps only if all active trades lead to one rate; with more rates
    # the invoice itself must decide (groups / manual choice).
    ares_rate = next(iter(ares_rate_ids)) if ares_rate_ids and len(ares_rate_ids) == 1 else None

    prepared = [prepare(i, store) for i in invoices]
    seen_keys: dict[str, Invoice] = {}
    seen_numbers: dict[tuple[str | None, str], Invoice] = {}
    counted_invoices: list[Invoice] = []
    auto_assigned = 0

    for invoice in sorted(prepared, key=lambda i: (i.issue_date or date.max, str(i.source))):
        paid, confirmed = payment_date(invoice, store)
        row_year = paid.year if paid else None
        if row_year is not None and row_year != year:
            continue
        number = invoice.number or invoice.source.name
        issues: list[Issue] = []

        def add(code, severity, **params):
            issues.append(Issue(code, severity, invoice.source, {"number": number, **params}))  # noqa: B023

        issued_by_me = my_ico is None or invoice.supplier_ico == my_ico
        counted = issued_by_me and invoice.doc_type.counted

        if not issued_by_me:
            add(
                IssueCode.INVOICE_RECEIVED,
                Severity.INFO,
                supplier=invoice.supplier_name or invoice.supplier_ico,
            )
        elif not invoice.doc_type.counted:
            add(IssueCode.INVOICE_ADVANCE, Severity.INFO)

        if counted and invoice.key in seen_keys:
            add(IssueCode.INVOICE_DUPLICATE, Severity.INFO, original=seen_keys[invoice.key].source.name)
            counted = False
        number_key = (invoice.supplier_ico, invoice.number) if invoice.number else None
        if counted and number_key and number_key in seen_numbers:
            other = seen_numbers[number_key]
            if other.amount == invoice.amount:
                add(IssueCode.INVOICE_DUPLICATE, Severity.INFO, original=other.source.name)
            else:
                add(
                    IssueCode.INVOICE_CONFLICT,
                    Severity.ERROR,
                    amount=_czk(invoice.amount),
                    other_amount=_czk(other.amount),
                )
            counted = False

        if counted and invoice.needs_review:
            add(IssueCode.INVOICE_NEEDS_REVIEW, Severity.WARNING, origin=invoice.origin.value)
        if counted and invoice.amount is None:
            add(IssueCode.INVOICE_NO_AMOUNT, Severity.ERROR)
            counted = False
        if paid is None:
            add(IssueCode.INVOICE_NO_DATE, Severity.ERROR)
            counted = False
        elif counted and not confirmed and invoice.issue_date and invoice.issue_date.year != paid.year:
            add(
                IssueCode.INVOICE_PAYMENT_UNCONFIRMED,
                Severity.WARNING,
                issue_year=invoice.issue_date.year,
                due=_cz(paid),
                year=paid.year,
            )

        rate_id, source = None, None
        if counted:
            seen_keys[invoice.key] = invoice
            if number_key:
                seen_numbers[number_key] = invoice
            rate_id, source = _choose_rate(invoice, store, ares_rate)
            if source == RateSource.GROUP:
                auto_assigned += 1
            counted_invoices.append(invoice)

        report.rows.append(
            InvoiceRow(
                invoice, paid, confirmed, row_year, counted, issued_by_me, rate_id, source, tuple(issues)
            )
        )

    # Groups are built from the counted invoices of the year; the GUI uses
    # them to assign one rate to many invoices at once.
    report.groups = group_invoices(counted_invoices)
    group_of = {inv.key: g.id for g in report.groups for inv in g.invoices}
    report.rows = [_with_group(r, group_of.get(r.invoice.key)) for r in report.rows]

    income: dict[str, Decimal] = defaultdict(Decimal)
    unassigned_count = 0
    for row in report.counted:
        amount = row.invoice.signed_amount or Decimal(0)
        if row.rate_id:
            income[row.rate_id] += amount
        else:
            report.unassigned += amount
            unassigned_count += 1
    report.rate_income = dict(income)

    if unassigned_count:
        report.issues.append(
            Issue(
                IssueCode.INVOICES_UNASSIGNED,
                Severity.ERROR,
                None,
                {"count": unassigned_count, "amount": format_czk(report.unassigned)},
            )
        )
    if auto_assigned:
        report.issues.append(
            Issue(IssueCode.INVOICES_AUTO_ASSIGNED, Severity.INFO, None, {"count": auto_assigned})
        )
    report.issues.extend(_number_gaps(counted_invoices))
    return report


def _choose_rate(
    invoice: Invoice, store: InvoiceStore, ares_rate: str | None
) -> tuple[str | None, str | None]:
    # The user's explicit choice always wins, then a group the user defined
    # earlier, and only then the automatic ARES suggestion.
    if invoice.key in store.manual_rates:
        return store.manual_rates[invoice.key], RateSource.MANUAL
    profile = best_profile(invoice, store.profiles)
    if profile is not None:
        return profile.rate_id, RateSource.GROUP
    if ares_rate:
        return ares_rate, RateSource.ARES
    return None, None


def _with_group(row: InvoiceRow, group_id: str | None) -> InvoiceRow:
    if group_id is None:
        return row
    return InvoiceRow(
        row.invoice,
        row.payment_date,
        row.payment_confirmed,
        row.tax_year,
        row.counted,
        row.issued_by_me,
        row.rate_id,
        row.rate_source,
        row.issues,
        group_id,
    )


_NUMBER_RE = re.compile(r"^(.*?)(\d+)$")


def _number_gaps(invoices: list[Invoice]) -> list[Issue]:
    """Missing numbers inside a numbering series ("2026001, 2026003").

    A series = same text prefix and same length of the trailing number.
    Only small gaps are reported: a jump by hundreds means a different
    series, not a hundred missing invoices.
    """
    series: dict[tuple[str, int], list[int]] = defaultdict(list)
    for invoice in invoices:
        match = _NUMBER_RE.match(invoice.number or "")
        if match:
            prefix, digits = match.groups()
            series[(prefix, len(digits))].append(int(digits))
    issues = []
    for (prefix, width), numbers in series.items():
        ordered = sorted(set(numbers))
        missing = [
            n for a, b in zip(ordered, ordered[1:], strict=False) if 1 < b - a <= 10 for n in range(a + 1, b)
        ]
        if missing:
            text = ", ".join(f"{prefix}{n:0{width}d}" for n in missing[:10])
            issues.append(Issue(IssueCode.INVOICE_NUMBER_GAP, Severity.INFO, None, {"missing": text}))
    return issues


def _czk(value: Decimal | None) -> str:
    return format_czk(value, 2) if value is not None else "?"


def _cz(d: date) -> str:
    return f"{d.day}.{d.month}.{d.year}"
