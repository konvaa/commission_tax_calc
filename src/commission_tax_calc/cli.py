"""Command-line interface - the same core, without a GUI.

Reads commission statements and issued invoices (ISDOC, PDF text, OCR).

Useful for scripting and as living proof that the domain logic does not
depend on Qt. Output is English; the GUI is the localized front-end.

    commission-tax-calc-cli ./statements --year 2024
    commission-tax-calc-cli ./statements --year 2024 --mode payout --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .core.aggregator import YearMode, available_years, build_report
from .core.ares import suggested_rate_ids
from .core.invoice_report import build_invoice_report, invoice_years
from .core.invoice_store import InvoiceStore
from .core.issues import Issue
from .core.loader import find_documents, load_documents
from .core.money import format_czk
from .core.paths import rules_cache_dir, user_data_dir
from .core.rules import RulesError, RulesRepository
from .core.tax import TaxSummary, compute


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.folder.is_dir():
        print(f"Not a folder: {args.folder}", file=sys.stderr)
        return 2

    repo = RulesRepository(rules_cache_dir())
    if args.update_rules:
        try:
            result = repo.update_from_remote()
            print(f"Rules updated for: {result.updated_years or 'nothing new'}", file=sys.stderr)
        except (OSError, RulesError) as exc:
            print(f"Rules update failed: {exc}", file=sys.stderr)

    mode = YearMode(args.mode)
    # Invoice decisions made in the GUI (own IČO, rates, payment dates) are
    # read from the same store, so the CLI gives the same numbers.
    store = InvoiceStore.load(user_data_dir() / "invoices.json")
    if args.my_ico:
        store.my_ico = args.my_ico
    loaded = load_documents(find_documents(args.folder, recursive=args.recursive), my_ico=store.my_ico)
    years = sorted(set(available_years(loaded.statements, mode)) | invoice_years(loaded.invoices, store))
    if not years:
        print("No statements or invoices found.", file=sys.stderr)
        _print_issues(loaded.failures)
        return 1
    year = args.year or max(years)

    report = build_report(loaded.statements, year, mode)
    rules, exact = repo.get(year)
    if rules is None:
        print("No flat-rate rules available.", file=sys.stderr)
        return 1
    ares = store.ares.get(store.my_ico or "")
    ares_rates = suggested_rate_ids(ares, rules, date(year, 12, 31)) if ares else None
    invoices = build_invoice_report(loaded.invoices, year, store, ares_rates)
    tax = compute(report.activity_totals, rules, None, invoices.rate_income, invoices.unassigned)
    issues = loaded.failures + report.all_issues() + invoices.all_issues() + tax.issues

    if args.json:
        data = _as_json(year, mode, report, tax, issues, exact)
        data["invoices_total"] = str(invoices.total)
        data["invoices"] = [
            {
                "file": row.invoice.source.name,
                "number": row.invoice.number,
                "paid": row.payment_date.isoformat() if row.payment_date else None,
                "amount": str(row.invoice.signed_amount) if row.invoice.signed_amount is not None else None,
                "counted": row.counted,
                "rate_id": row.rate_id,
            }
            for row in invoices.rows
        ]
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        _print_text(year, mode, report, tax, issues, exact, rules.tax_year)
        if invoices.rows:
            print(f"  Issued invoices: {len(invoices.counted)} counted, {format_czk(invoices.total, 2)}")
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="commission-tax-calc-cli",
        description="Sum FinTrust commission statements (PDF) for the Czech tax return.",
    )
    p.add_argument("folder", type=Path, help="folder with downloaded statements")
    p.add_argument("--year", type=int, help="tax year (default: the latest found)")
    p.add_argument(
        "--mode",
        choices=[m.value for m in YearMode],
        default=YearMode.BY_PERIOD.value,
        help="assign statements by period (default) or by expected payout",
    )
    p.add_argument("--recursive", action="store_true", help="search subfolders too")
    p.add_argument("--my-ico", help="your IČO (invoices issued by others are ignored)")
    p.add_argument("--update-rules", action="store_true", help="download newer rules first")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    return p


def _print_text(year, mode, report, tax: TaxSummary, issues, exact, rules_year) -> None:
    print(f"Tax year {year} (mode: {mode.value}) - {len(report.counted)} statement(s) counted")
    print(f"  Commission total ('Provize celkem'): {format_czk(report.total)}")
    if not exact:
        print(f"  ! using flat-rate rules for {rules_year}")
    for line in tax.lines:
        cap = " (capped)" if line.capped else ""
        print(
            f"  {line.rate.percent}% {line.rate.name.get('en', line.rate.id)}: "
            f"income {format_czk(line.income)}, expenses {format_czk(line.expenses)}{cap}, "
            f"partial base {format_czk(line.partial_base)}"
        )
    print(f"  Partial tax base § 7: {format_czk(tax.partial_base)}")
    _print_issues(issues)


def _print_issues(issues: list[Issue]) -> None:
    for issue in issues:
        where = f" [{issue.source.name}]" if issue.source else ""
        print(f"  {issue.severity.name}{where}: {issue.message()}")


def _as_json(year, mode, report, tax: TaxSummary, issues, exact) -> dict:
    # Decimals are emitted as strings so no precision is lost in JSON.
    return {
        "year": year,
        "mode": mode.value,
        "rules_exact_year": exact,
        "commission_total": str(report.total),
        "statements": [
            {
                "file": row.statement.source.name,
                "period": [row.statement.period.start.isoformat(), row.statement.period.end.isoformat()],
                "total": str(row.statement.summary.total),
                "counted": row.counted,
            }
            for row in report.rows
        ],
        "rates": [
            {
                "rate_id": line.rate.id,
                "percent": str(line.rate.percent),
                "activities": list(line.activities),
                "income": str(line.income),
                "expenses": str(line.expenses),
                "partial_base": str(line.partial_base),
                "capped": line.capped,
            }
            for line in tax.lines
        ],
        "partial_tax_base": str(tax.partial_base),
        "issues": [
            {
                "code": i.code.value,
                "severity": i.severity.name,
                "file": i.source.name if i.source else None,
                "message": i.message(),
            }
            for i in issues
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
