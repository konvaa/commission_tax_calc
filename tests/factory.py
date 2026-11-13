"""Synthetic commission statements for tests.

Real statements contain client names and contract numbers, so they must never
be committed (GDPR). This module produces text in exactly the shape that
pdfplumber extracts from a real FinTrust statement, with invented people and
numbers. ``make_pdf`` renders the same text into a PDF for end-to-end tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

DEFAULT_ACTIVITY = (
    "Není živností, řídí se zvláštním předpisem",
    (
        "Zprostředkování pojištění",
        "Zprostředkování investic",
        "Zprostředkování doplňkového penzijního spoření (III. pilíř důchodové reformy)",
        "Zprostředkování úvěrů",
    ),
)


def czk(value: Decimal | int | str) -> str:
    """Format like the statement: '1 128,47 Kč', '-4 418 Kč' (normal spaces)."""
    value = Decimal(str(value))
    sign = "-" if value < 0 else ""
    integer, _, fraction = f"{abs(value):f}".partition(".")
    groups = []
    while integer:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    text = " ".join(groups) or "0"
    if fraction and fraction.strip("0"):
        text += "," + fraction[:2].ljust(2, "0")
    return f"{sign}{text} Kč"


@dataclass
class Spec:
    start: date = date(2030, 1, 1)
    end: date = date(2030, 1, 14)
    holder: str = "Testovací Tomáš"
    # rows: (client, contract, product, partner, commission)
    rows: list[tuple[str, str, str, str, int]] = field(
        default_factory=lambda: [
            ("Fiktivní Klára", "1000000001", "Domácnost Plus", "Vymyšlená pojišťovna, a.s.", 1000)
        ]
    )
    inter_commissions: int = 0
    holding: int = 0
    extraordinary: int = 0
    deductions: int = 0
    released: int = 0
    paid_to_reserve: int = 0
    payout: Decimal | None = None
    # activities: (heading, bullet items, amount); None = everything in DEFAULT_ACTIVITY
    activities: list[tuple[str, tuple[str, ...], int]] | None = None
    total_override: int | None = None

    @property
    def commissions(self) -> int:
        return sum(r[4] for r in self.rows)

    @property
    def regular(self) -> int:
        return self.commissions + self.inter_commissions + self.holding

    @property
    def total(self) -> int:
        if self.total_override is not None:
            return self.total_override
        return self.regular + self.extraordinary


def make_text(spec: Spec | None = None, **changes) -> str:
    spec = spec or Spec(**changes)
    payout = spec.payout
    if payout is None:
        payout = Decimal(spec.total + spec.released + spec.paid_to_reserve - spec.deductions)
    activities = spec.activities
    if activities is None:
        activities = [(DEFAULT_ACTIVITY[0], DEFAULT_ACTIVITY[1], spec.total)]

    d = lambda x: f"{x.day}.{x.month}.{x.year}"  # noqa: E731
    lines = [
        "Provizní sestava",
        f"Období: {d(spec.start)} - {d(spec.end)}",
        spec.holder,
        "Shrnutí",
        f"Provize za běžné období {czk(spec.regular)}",
        f"Mimořádné provize {czk(spec.extraordinary)}",
        f"Provize celkem {czk(spec.total)}",
        f"Uvolněno ze stornofondu {czk(spec.released)}",
        f"Odvedeno do stornofondu {czk(spec.paid_to_reserve)}",
        f"K výplatě {czk(payout)}",
        "Provize",
        "Počet Kč /",
        "Klient Smlouva Produkt Partner Základ Typ bodů bod Provize Poznámka",
    ]
    for client, contract, product, partner, amount in spec.rows:
        # A wrapped product name, as in real statements.
        lines.append("Pojištění -")
        points = f"{amount / 100:.1f}".replace(".", ",")
        lines.append(f"{client} {contract} {product} {partner} 12345 Z {points} 100 {czk(amount)}")
    lines += [
        f"Celkem 0,0 {czk(spec.commissions)}",
        "Meziprovize",
        "Finanční poradce Body Provize",
        f"Celkem 0,0 {czk(spec.inter_commissions)}",
        "Holdingové provize",
        "Klient Smlouva Provizní základ Provize v % Provize v Kč",
        f"Celkem {czk(spec.holding)}",
        "Mimořádné provize",
        "Popis Provize",
        f"Celkem {czk(spec.extraordinary)}",
        "Exekuce a srážky",
        "Popis Provize",
        f"Celkem {czk(spec.deductions)}",
        "Stornofond",
        "Minulé období Aktuálně Změna",
        "Nezasloužená provize 0 Kč 0 Kč 0 Kč",
        "Stornofond NP 1 000 Kč 1 200 Kč 200 Kč",
        "Stornofond celkem 1 000 Kč 1 200 Kč 200 Kč",
        "Aktuální výše stornofondu 1 200 Kč je v pořádku.",
        "Rozdělení příjmů pro uplatnění paušálních výdajů dle § 7 odst. 7 zákona o daních z příjmů",
        "Druh činnosti Provize",
    ]
    for heading, items, amount in activities:
        lines.append(heading if items else f"{heading} {czk(amount)}")
        for i, item in enumerate(items):
            # The amount sits on the second bullet line, like in real files.
            suffix = f" {czk(amount)}" if i == min(1, len(items) - 1) else ""
            lines.append(f"• {item}{suffix}")
    return "\n".join(lines)


def find_font() -> Path | None:
    """A TTF font with Czech glyphs, or None (then PDF tests are skipped)."""
    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    ]
    return next((p for p in candidates if p.is_file()), None)


def make_pdf(path: Path, text: str, font: Path) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(TTFont("TestFont", str(font)))
    pdf = canvas.Canvas(str(path), pagesize=A4)
    _, height = A4
    y = height - 40
    for line in text.splitlines():
        if y < 40:  # continue on a new page, like a long real statement
            pdf.showPage()
            y = height - 40
        pdf.setFont("TestFont", 8)
        pdf.drawString(30, y, line)
        y -= 11
    pdf.save()
    return path


# ------------------------------------------------------------- invoices ---

SUPPLIER_ICO = "12345679"  # valid checksum, fictitious use
CUSTOMER_A = ("33333335", "Smyšlená stavební a.s.")
CUSTOMER_B = ("22222227", "Vymyšlené projekty s.r.o.")


@dataclass
class InvoiceSpec:
    number: str = "2030001"
    supplier_ico: str = SUPPLIER_ICO
    supplier_name: str = "Testovací Tomáš"
    customer_ico: str = CUSTOMER_A[0]
    customer_name: str = CUSTOMER_A[1]
    issue: date = date(2030, 3, 1)
    due: date = date(2030, 3, 15)
    lines: list[tuple[str, int]] = field(
        default_factory=lambda: [("Montáž elektroinstalace, byt č. 12", 10000)]
    )
    doc_type: int = 1
    vat: bool = False
    uuid: str | None = None
    note: str = "Fakturujeme Vám:"

    @property
    def total(self) -> int:
        return sum(amount for _, amount in self.lines)


def make_isdoc(spec: InvoiceSpec) -> bytes:
    """A minimal ISDOC 6 document with the elements the app reads."""
    import uuid as uuidlib
    from xml.sax.saxutils import escape

    total = spec.total
    with_vat = round(total * 1.21) if spec.vat else total
    lines = "".join(
        f"<InvoiceLine><ID>{i}</ID><LineExtensionAmount>{amount}.00</LineExtensionAmount>"
        f"<Item><Description>{escape(text)}</Description></Item></InvoiceLine>"
        for i, (text, amount) in enumerate(spec.lines, start=1)
    )
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<Invoice xmlns="http://isdoc.cz/namespace/2013" version="6.0.2">
  <DocumentType>{spec.doc_type}</DocumentType>
  <ID>{spec.number}</ID>
  <UUID>{spec.uuid or uuidlib.uuid5(uuidlib.NAMESPACE_URL, spec.number + spec.supplier_ico)}</UUID>
  <IssueDate>{spec.issue.isoformat()}</IssueDate>
  <TaxPointDate>{spec.issue.isoformat()}</TaxPointDate>
  <VATApplicable>{"true" if spec.vat else "false"}</VATApplicable>
  <Note>{escape(spec.note)}</Note>
  <AccountingSupplierParty><Party><PartyIdentification><ID>{spec.supplier_ico}</ID></PartyIdentification>
    <PartyName><Name>{escape(spec.supplier_name)}</Name></PartyName></Party></AccountingSupplierParty>
  <AccountingCustomerParty><Party><PartyIdentification><ID>{spec.customer_ico}</ID></PartyIdentification>
    <PartyName><Name>{escape(spec.customer_name)}</Name></PartyName></Party></AccountingCustomerParty>
  <InvoiceLines>{lines}</InvoiceLines>
  <LegalMonetaryTotal>
    <TaxExclusiveAmount>{total}.00</TaxExclusiveAmount>
    <TaxInclusiveAmount>{with_vat}.00</TaxInclusiveAmount>
    <PayableAmount>{with_vat}.00</PayableAmount>
  </LegalMonetaryTotal>
  <PaymentMeans><Payment><Details><PaymentDueDate>{spec.due.isoformat()}</PaymentDueDate></Details></Payment></PaymentMeans>
</Invoice>"""
    return xml.encode("utf-8")


def invoice_text(spec: InvoiceSpec) -> str:
    """Printed form of the invoice, laid out like a common Czech invoice."""
    d = lambda x: x.strftime("%d.%m.%Y")  # noqa: E731
    title = {2: "OPRAVNÝ DAŇOVÝ DOKLAD - DOBROPIS", 4: "ZÁLOHOVÁ FAKTURA"}.get(spec.doc_type, "FAKTURA")
    rows = [
        f"{spec.supplier_name} {title} č. {spec.number}",
        f"Dodavatel: Variabilní s.: {spec.number}",
        spec.supplier_name,
        "Testovací 1, 74401 Frenštát pod Radhoštěm",
        f"Odběratel: IČ: {spec.customer_ico}",
        spec.customer_name,
        f"IČ: {spec.supplier_ico}",
        f"Datum vystavení: {d(spec.issue)}",
        f"Datum splatnosti: {d(spec.due)}",
        "Firma není plátcem DPH." if not spec.vat else f"DUZP: {d(spec.issue)}",
        "Označení dodávky Množství J.cena Kč Celkem",
        spec.note,
    ]
    rows += [f"{text} 1 ks {czk(amount)[:-3]},00 {czk(amount)[:-3]},00" for text, amount in spec.lines]
    rows.append(f"Součet položek {czk(spec.total)[:-3]},00")
    if spec.vat:
        rows.append(f"Celkem bez DPH {czk(spec.total)[:-3]},00")
        rows.append(f"CELKEM K ÚHRADĚ {czk(round(spec.total * 1.21))[:-3]},00")
    else:
        rows.append(f"CELKEM K ÚHRADĚ Částky jsou uvedeny v Kč {czk(spec.total)[:-3]},00")
    return "\n".join(rows)


def make_invoice_pdf(path: Path, spec: InvoiceSpec, font: Path, embed_isdoc: bool = True) -> Path:
    make_pdf(path, invoice_text(spec), font)
    if embed_isdoc:
        import io

        import pypdfium2

        pdf = pypdfium2.PdfDocument(str(path))
        attachment = pdf.new_attachment("invoice.isdoc")
        attachment.set_data(make_isdoc(spec))
        buffer = io.BytesIO()
        pdf.save(buffer)
        pdf.close()
        path.write_bytes(buffer.getvalue())
    return path


def make_scanned_pdf(path: Path, spec: InvoiceSpec, font: Path) -> Path:
    """An image-only PDF (no text layer), like a scanned paper invoice."""
    import pypdfium2

    text_pdf = path.with_suffix(".tmp.pdf")
    make_invoice_pdf(text_pdf, spec, font, embed_isdoc=False)
    pdf = pypdfium2.PdfDocument(str(text_pdf))
    image = pdf[0].render(scale=200 / 72).to_pil().convert("RGB")
    pdf.close()
    text_pdf.unlink()
    image.save(path, "PDF", resolution=200)
    return path
