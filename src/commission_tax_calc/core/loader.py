"""Reading a folder of documents: commission statements and invoices.

The loader never raises for a single bad file: one corrupted download must not
hide the results of the other twenty-three. Failures are returned as issues.

Each file is classified by its *content*, not by its name, in this order -
cheapest and most reliable first:

1. ``.isdoc`` / ``.isdocx`` file, or a PDF with embedded ISDOC -> invoice (exact),
2. PDF text starting with "Provizní sestava" -> FinTrust commission statement,
3. PDF text that looks like an invoice -> invoice (heuristics, needs review),
4. PDF without text (a scan) -> OCR -> invoice (heuristics, needs review).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .invoice_models import Invoice, Origin
from .invoice_text import looks_like_invoice, parse_invoice_text
from .isdoc import IsdocError, extract_from_pdf, file_key, parse_isdoc, read_isdoc_file
from .issues import Issue, IssueCode, Severity
from .models import Statement
from .ocr import OcrUnavailable, ocr_pdf
from .parser import ParseError, extract_text, parse_file, parse_text

# progress(done, total, current_file)
ProgressCallback = Callable[[int, int, Path], None]

DOCUMENT_SUFFIXES = {".pdf", ".isdoc", ".isdocx"}
# A real text layer has hundreds of characters; scans often carry a few
# stray characters (a scanner's header), which must not count as "text".
_MIN_TEXT_CHARS = 50


@dataclass
class LoadResult:
    statements: list[Statement] = field(default_factory=list)
    invoices: list[Invoice] = field(default_factory=list)
    failures: list[Issue] = field(default_factory=list)


def find_pdfs(folder: Path, recursive: bool = False) -> list[Path]:
    return find_documents(folder, recursive, suffixes={".pdf"})


def find_documents(folder: Path, recursive: bool = False, suffixes: set[str] | None = None) -> list[Path]:
    suffixes = suffixes or DOCUMENT_SUFFIXES
    pattern = "**/*" if recursive else "*"
    # Sort by name so the "first" file of a duplicate pair is deterministic.
    # Case-insensitive suffix check: Windows downloads may end with ".PDF".
    return sorted(
        (p for p in folder.glob(pattern) if p.is_file() and p.suffix.lower() in suffixes),
        key=lambda p: str(p).casefold(),
    )


def load_statements(
    paths: Iterable[Path],
    progress: ProgressCallback | None = None,
    parse: Callable[[Path], Statement] = parse_file,
) -> LoadResult:
    """Parse commission statements only. ``parse`` is injectable for tests."""
    paths = list(paths)
    result = LoadResult()
    for index, path in enumerate(paths, start=1):
        try:
            result.statements.append(parse(path))
        except ParseError as exc:
            result.failures.append(_failed(path, str(exc)))
        if progress:
            progress(index, len(paths), path)
    return result


def load_documents(
    paths: Iterable[Path],
    progress: ProgressCallback | None = None,
    my_ico: str | None = None,
    ocr: Callable[[Path], str] = ocr_pdf,
) -> LoadResult:
    paths = list(paths)
    result = LoadResult()
    for index, path in enumerate(paths, start=1):
        try:
            _load_one(path, result, my_ico, ocr)
        except (ParseError, IsdocError, OSError) as exc:
            result.failures.append(_failed(path, str(exc)))
        if progress:
            progress(index, len(paths), path)
    return result


def _load_one(path: Path, result: LoadResult, my_ico: str | None, ocr: Callable[[Path], str]) -> None:
    suffix = path.suffix.lower()
    if suffix in {".isdoc", ".isdocx"}:
        result.invoices.append(parse_isdoc(read_isdoc_file(path), path))
        return

    xml = extract_from_pdf(path)
    text, pages = extract_text(path)
    if xml is not None:
        result.invoices.append(parse_isdoc(xml, path, page_count=pages))
        return

    head = "\n".join(text.strip().splitlines()[:5])
    if "Provizní sestava" in head:
        statement = parse_text(text, source=path)
        result.statements.append(
            Statement(
                source=statement.source,
                holder=statement.holder,
                period=statement.period,
                summary=statement.summary,
                sections=statement.sections,
                activities=statement.activities,
                reserve_balance=statement.reserve_balance,
                page_count=pages,
            )
        )
        return

    key = file_key(path.read_bytes())
    if len(text.strip()) >= _MIN_TEXT_CHARS:
        origin = Origin.TEXT
    else:
        origin = Origin.OCR
        try:
            text = ocr(path)
        except OcrUnavailable as exc:
            # Still list the scan as an invoice: the user can type the values
            # in the review dialog. Silently dropping it would lose income.
            result.invoices.append(Invoice(source=path, origin=Origin.OCR, key=key, page_count=pages))
            result.failures.append(
                Issue(IssueCode.OCR_UNAVAILABLE, Severity.WARNING, path, {"reason": str(exc)})
            )
            return

    if not looks_like_invoice(text):
        result.failures.append(Issue(IssueCode.UNKNOWN_DOCUMENT, Severity.WARNING, path))
        return
    invoice = parse_invoice_text(text, path, key, origin, my_ico, pages)
    result.invoices.append(invoice.with_changes(raw_text=text))


def _failed(path: Path, reason: str) -> Issue:
    return Issue(IssueCode.PARSE_FAILED, Severity.ERROR, path, {"reason": reason})
