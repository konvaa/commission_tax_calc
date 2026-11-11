"""Reading a folder of statements.

The loader never raises for a single bad file: one corrupted download must not
hide the results of the other twenty-three. Failures are returned as issues.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .issues import Issue, IssueCode, Severity
from .models import Statement
from .parser import ParseError, parse_file

# progress(done, total, current_file)
ProgressCallback = Callable[[int, int, Path], None]


@dataclass
class LoadResult:
    statements: list[Statement] = field(default_factory=list)
    failures: list[Issue] = field(default_factory=list)


def find_pdfs(folder: Path, recursive: bool = False) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    # Sort by name so the "first" file of a duplicate pair is deterministic.
    # Case-insensitive suffix check: Windows downloads may end with ".PDF".
    return sorted(
        (p for p in folder.glob(pattern) if p.is_file() and p.suffix.lower() == ".pdf"),
        key=lambda p: str(p).casefold(),
    )


def load_statements(
    paths: Iterable[Path],
    progress: ProgressCallback | None = None,
    parse: Callable[[Path], Statement] = parse_file,
) -> LoadResult:
    """Parse all given files. ``parse`` is injectable to keep tests PDF-free."""
    paths = list(paths)
    result = LoadResult()
    for index, path in enumerate(paths, start=1):
        try:
            result.statements.append(parse(path))
        except ParseError as exc:
            result.failures.append(Issue(IssueCode.PARSE_FAILED, Severity.ERROR, path, {"reason": str(exc)}))
        if progress:
            progress(index, len(paths), path)
    return result
