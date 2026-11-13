"""Review dialog: the invoice PDF on the left, the values read from it on the right.

Shown for invoices read from PDF text or OCR (and on request for any other).
The user compares, fixes what the heuristics got wrong and confirms - from
then on the invoice counts as verified and the corrections are remembered.

``QPdfView`` (QtPdf) renders the PDF natively inside Qt; no need to convert
pages to images ourselves, and zooming/scrolling come for free.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate, QEvent, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..core.ico import is_valid
from ..core.invoice_models import DocType, Invoice


class ReviewDialog(QDialog):
    def __init__(self, invoice: Invoice, parent=None) -> None:
        super().__init__(parent)
        self._invoice = invoice
        self.resize(1150, 760)

        # -- PDF preview ---------------------------------------------------
        self.document = QPdfDocument(self)
        self.preview = QPdfView()
        self.preview.setDocument(self.document)
        self.preview.setPageMode(QPdfView.PageMode.MultiPage)
        self.preview.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        if invoice.source.suffix.lower() == ".pdf":
            self.document.load(str(invoice.source))

        # -- fields --------------------------------------------------------
        self.number = QLineEdit(invoice.number or "")
        self.doc_type = QComboBox()
        for kind in DocType:
            self.doc_type.addItem("", kind)
        self.doc_type.setCurrentIndex(self.doc_type.findData(invoice.doc_type))
        ico_validator = QRegularExpressionValidator(r"\d{0,8}")
        self.supplier_ico = QLineEdit(invoice.supplier_ico or "")
        self.supplier_ico.setValidator(ico_validator)
        self.customer_ico = QLineEdit(invoice.customer_ico or "")
        self.customer_ico.setValidator(ico_validator)
        self.customer_name = QLineEdit(invoice.customer_name or "")
        self.issue_date = self._date_edit(invoice.issue_date)
        self.due_date = self._date_edit(invoice.due_date)
        self.amount = QLineEdit("" if invoice.amount is None else f"{invoice.amount:.2f}".replace(".", ","))
        self.amount.setValidator(QRegularExpressionValidator(r"[\d\s]*([,.]\d{0,2})?"))
        self.vat_payer = QCheckBox()
        self.vat_payer.setChecked(invoice.vat_payer)

        self.form = QFormLayout()
        self.labels = {}
        for key, widget in (
            ("number", self.number),
            ("doc_type", self.doc_type),
            ("supplier_ico", self.supplier_ico),
            ("customer_ico", self.customer_ico),
            ("customer_name", self.customer_name),
            ("issue_date", self.issue_date),
            ("due_date", self.due_date),
            ("amount", self.amount),
            ("vat_payer", self.vat_payer),
        ):
            label = QLabel()
            self.labels[key] = label
            self.form.addRow(label, widget)

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        self.buttons = buttons

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.hint)
        right_layout.addLayout(self.form)
        right_layout.addStretch()
        right_layout.addWidget(buttons)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.preview)
        splitter.addWidget(right)
        splitter.setSizes([700, 450])
        QVBoxLayout(self).addWidget(splitter)
        self.retranslate_ui()

    @staticmethod
    def _date_edit(value: date | None) -> QDateEdit:
        edit = QDateEdit()
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("d.M.yyyy")
        edit.setDate(QDate(value.year, value.month, value.day) if value else QDate.currentDate())
        return edit

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.tr("Check invoice – {0}").format(self._invoice.source.name))
        self.hint.setText(
            self.tr(
                "These values were read automatically. Compare them with the invoice on the left, "
                "fix what is wrong and confirm. For VAT payers enter the amount without VAT."
            )
        )
        texts = {
            "number": self.tr("Invoice number:"),
            "doc_type": self.tr("Document type:"),
            "supplier_ico": self.tr("Supplier IČO:"),
            "customer_ico": self.tr("Customer IČO:"),
            "customer_name": self.tr("Customer:"),
            "issue_date": self.tr("Issue date:"),
            "due_date": self.tr("Due date:"),
            "amount": self.tr("Amount (income):"),
            "vat_payer": self.tr("Supplier is a VAT payer:"),
        }
        for key, label in self.labels.items():
            label.setText(texts[key])
        names = {
            DocType.INVOICE: self.tr("Invoice"),
            DocType.CREDIT_NOTE: self.tr("Credit note (subtracted)"),
            DocType.DEBIT_NOTE: self.tr("Debit note"),
            DocType.ADVANCE: self.tr("Advance invoice (not counted)"),
        }
        for i in range(self.doc_type.count()):
            self.doc_type.setItemText(i, names[self.doc_type.itemData(i)])
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("Confirm"))

    def _accept(self) -> None:
        for edit, label in ((self.supplier_ico, "supplier_ico"), (self.customer_ico, "customer_ico")):
            if edit.text() and not is_valid(edit.text()):
                QMessageBox.warning(
                    self,
                    self.windowTitle(),
                    self.tr("{0} {1} is not a valid IČO (checksum does not match).").format(
                        self.labels[label].text().rstrip(":"), edit.text()
                    ),
                )
                edit.setFocus()
                return
        if self.amount_value() is None:
            QMessageBox.warning(self, self.windowTitle(), self.tr("Enter the amount."))
            self.amount.setFocus()
            return
        self.accept()

    def amount_value(self) -> Decimal | None:
        raw = self.amount.text().replace(" ", "").replace(" ", "").replace(",", ".")
        try:
            return Decimal(raw).quantize(Decimal("0.01")) if raw else None
        except InvalidOperation:
            return None

    def values(self) -> dict:
        """Corrected values in the format ``InvoiceStore.set_correction`` expects."""

        def to_date(edit: QDateEdit) -> date:
            q = edit.date()
            return date(q.year(), q.month(), q.day())

        return {
            "number": self.number.text().strip() or None,
            "doc_type": self.doc_type.currentData(),
            "supplier_ico": self.supplier_ico.text().strip() or None,
            "customer_ico": self.customer_ico.text().strip() or None,
            "customer_name": self.customer_name.text().strip() or None,
            "issue_date": to_date(self.issue_date),
            "due_date": to_date(self.due_date),
            "amount": self.amount_value(),
            "vat_payer": self.vat_payer.isChecked(),
        }
