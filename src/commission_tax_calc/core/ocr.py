"""OCR of scanned (image-only) PDFs with Tesseract.

Tesseract is a separate program, not a Python package; ``pytesseract`` only
calls it. The app therefore looks for it in this order:

1. bundled next to the frozen .exe (the release build ships it),
2. ``TESSERACT_CMD`` environment variable,
3. on PATH,
4. the default Windows installation folder.

If none is found, OCR is reported as unavailable and scanned invoices are
still listed - the user types the values in the review dialog instead.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

LANGUAGE = "ces"
_DPI = 300  # standard OCR resolution; lower loses diacritics, higher is slow


class OcrUnavailable(RuntimeError):
    """Tesseract or its Czech language data is not installed."""


def find_tesseract() -> tuple[str, str | None] | None:
    """Return ``(executable, tessdata_dir or None)`` or ``None``."""
    bundle = getattr(sys, "_MEIPASS", None)  # PyInstaller extraction folder
    if bundle:
        exe = Path(bundle) / "tesseract" / "tesseract.exe"
        if exe.is_file():
            return str(exe), str(exe.parent / "tessdata")
    for candidate in (os.environ.get("TESSERACT_CMD"), shutil.which("tesseract")):
        if candidate and Path(candidate).is_file():
            return candidate, None
    # Environment variable names are case-insensitive on Windows.
    program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    default = program_files / "Tesseract-OCR" / "tesseract.exe"
    if default.is_file():
        return str(default), None
    return None


def ocr_pdf(path: Path, max_pages: int = 5) -> str:
    """Render pages with pdfium and read them with Tesseract.

    Only the first pages are read: invoices are short and an accidental
    100-page scan should not freeze the run for minutes.
    """
    found = find_tesseract()
    if found is None:
        raise OcrUnavailable("Tesseract OCR is not installed")
    exe, tessdata = found

    import pypdfium2
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = exe
    config = "--psm 6"  # "a single uniform block of text" works best for invoices
    if tessdata:
        config += f' --tessdata-dir "{tessdata}"'
    try:
        if LANGUAGE not in pytesseract.get_languages(config=config):
            raise OcrUnavailable("Czech language data (ces.traineddata) is not installed")
    except pytesseract.TesseractError as exc:
        raise OcrUnavailable(str(exc)) from exc

    pdf = pypdfium2.PdfDocument(str(path))
    try:
        texts = []
        for index in range(min(len(pdf), max_pages)):
            image = pdf[index].render(scale=_DPI / 72).to_pil().convert("L")
            texts.append(pytesseract.image_to_string(image, lang=LANGUAGE, config=config))
        return "\n".join(texts)
    finally:
        pdf.close()
