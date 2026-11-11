from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the helper module ``factory`` importable regardless of pytest's import mode.
sys.path.insert(0, str(Path(__file__).parent))

from commission_tax_calc.core.parser import parse_text  # noqa: E402
from factory import Spec, make_text  # noqa: E402


@pytest.fixture
def statement():
    """Build a parsed Statement from keyword arguments of ``factory.Spec``."""

    def build(name: str = "s.pdf", **changes):
        return parse_text(make_text(Spec(**changes)), source=Path(name))

    return build
