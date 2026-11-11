from decimal import Decimal
from pathlib import Path

import pytest

from commission_tax_calc.core.issues import IssueCode
from commission_tax_calc.core.loader import find_pdfs, load_statements
from commission_tax_calc.core.parser import ParseError, parse_file, parse_text
from factory import Spec, find_font, make_pdf, make_text


def test_find_pdfs_filters_and_sorts(tmp_path):
    for name in ["b.pdf", "A.PDF", "notes.txt"]:
        (tmp_path / name).write_text("x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.pdf").write_text("x")
    assert [p.name for p in find_pdfs(tmp_path)] == ["A.PDF", "b.pdf"]
    assert [p.name for p in find_pdfs(tmp_path, recursive=True)] == ["A.PDF", "b.pdf", "c.pdf"]


def test_one_bad_file_does_not_stop_the_rest():
    def parse(path: Path):
        if path.name == "bad.pdf":
            raise ParseError("broken")
        return parse_text(make_text(Spec()), source=path)

    progress = []
    result = load_statements(
        [Path("ok.pdf"), Path("bad.pdf")], progress=lambda d, t, p: progress.append((d, t)), parse=parse
    )
    assert len(result.statements) == 1
    assert result.failures[0].code is IssueCode.PARSE_FAILED
    assert progress == [(1, 2), (2, 2)]


def test_not_a_pdf_is_a_parse_error(tmp_path):
    fake = tmp_path / "fake.pdf"
    fake.write_text("this is not a PDF")
    with pytest.raises(ParseError):
        parse_file(fake)


FONT = find_font()


@pytest.mark.skipif(FONT is None, reason="no TTF font with Czech glyphs found")
def test_end_to_end_pdf(tmp_path):
    """Render a synthetic statement to PDF and read it back with pdfplumber."""
    spec = Spec(
        rows=[("Smyšlená Žofie", "999", "Životní pojištění", "Pojišťovna, a.s.", 29952)],
        paid_to_reserve=-4418,
    )
    pdf = make_pdf(tmp_path / "statement.pdf", make_text(spec), FONT)
    st = parse_file(pdf)
    assert st.summary.total == Decimal(29952)
    assert st.summary.payout == Decimal(25534)
    assert st.activities[0].amount == Decimal(29952)
    assert st.page_count == 1


@pytest.mark.skipif(FONT is None, reason="no TTF font with Czech glyphs found")
def test_multi_page_pdf(tmp_path):
    rows = [(f"Klient {i}", str(i), "Produkt", "Partner, a.s.", 100) for i in range(40)]
    pdf = make_pdf(tmp_path / "long.pdf", make_text(Spec(rows=rows)), FONT)
    st = parse_file(pdf)
    assert st.page_count > 1
    assert st.summary.total == Decimal(4000)
    assert st.sections.commissions == Decimal(4000)
