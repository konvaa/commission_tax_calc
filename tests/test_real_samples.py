"""Optional regression test on *your own* statements - never committed.

    # Windows (PowerShell)
    $env:COMMISSION_SAMPLES_DIR = "F:\\Projekty\\Tax_Calc\\vzory"; pytest tests/test_real_samples.py -v

Skipped when the variable is not set (always the case in CI).
"""

import os
from pathlib import Path

import pytest

from commission_tax_calc.core.issues import Severity
from commission_tax_calc.core.loader import find_pdfs, load_statements
from commission_tax_calc.core.validation import validate_statement

SAMPLES = os.environ.get("COMMISSION_SAMPLES_DIR")

pytestmark = pytest.mark.skipif(not SAMPLES, reason="COMMISSION_SAMPLES_DIR not set")


def test_all_samples_parse_without_warnings():
    paths = find_pdfs(Path(SAMPLES))
    assert paths, "no PDFs in COMMISSION_SAMPLES_DIR"
    result = load_statements(paths)
    assert result.failures == []
    for st in result.statements:
        problems = [i for i in validate_statement(st) if i.severity > Severity.INFO]
        assert problems == [], f"{st.source.name}: {[i.message() for i in problems]}"
