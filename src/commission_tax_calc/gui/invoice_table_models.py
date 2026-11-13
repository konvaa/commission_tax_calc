"""Qt models for the invoice table and the invoice groups, plus the rate editor.

Editing in Qt Model/View works differently from a typical Python UI where a
button opens a form and the form writes to your data:

* the model declares a cell editable via ``flags()`` (``ItemIsEditable``),
* the *view* asks a *delegate* to create an editor widget for that cell,
* the delegate writes the result back through ``model.setData()``.

So the table itself is the form. For a ``QDate`` value the default delegate
already creates a ``QDateEdit``; for the rate we need a ``QComboBox`` - that
is what ``RateDelegate`` provides. The models do not change any state
themselves: ``setData`` emits a signal and the main window updates the
store and recomputes, keeping a single place where decisions are saved.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QAbstractTableModel, QDate, QModelIndex, QPersistentModelIndex, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QComboBox, QStyledItemDelegate

from ..core.grouping import InvoiceGroup
from ..core.invoice_models import DocType, Origin
from ..core.invoice_report import InvoiceReport, InvoiceRow, RateSource
from ..core.issues import Severity
from ..core.money import format_czk
from ..core.rules import RuleSet, text
from .issue_texts import issue_text
from .table_models import SORT_ROLE, severity_icon

_Index = QModelIndex | QPersistentModelIndex
_ROOT = QModelIndex()
RATE_ROLE = Qt.ItemDataRole.UserRole + 2  # the rate id behind the displayed label


def rate_label(rules: RuleSet | None, rate_id: str | None, language: str) -> str:
    if rules is None or rate_id is None:
        return "—"
    rate = rules.rate(rate_id)
    return f"{rate.percent} % – {text(rate.name, language)}" if rate else rate_id


class RateDelegate(QStyledItemDelegate):
    """Combo box editor listing the flat-rate categories of the current rules."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.rules: RuleSet | None = None
        self.language = "cs"

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.addItem(self.tr("— no rate —"), None)
        for rate in self.rules.rates if self.rules else ():
            combo.addItem(f"{rate.percent} % – {text(rate.name, self.language)}", rate.id)
        # Commit on the first click instead of waiting for focus to leave the
        # cell - picking a rate should feel like a single action.
        combo.activated.connect(lambda: (self.commitData.emit(combo), self.closeEditor.emit(combo)))
        return combo

    def setEditorData(self, editor: QComboBox, index) -> None:
        position = editor.findData(index.data(RATE_ROLE))
        editor.setCurrentIndex(max(position, 0))
        editor.showPopup()

    def setModelData(self, editor: QComboBox, model, index) -> None:
        model.setData(index, editor.currentData(), Qt.ItemDataRole.EditRole)


class InvoicesModel(QAbstractTableModel):
    NUMBER, CUSTOMER, ISSUED, PAID, AMOUNT, RATE, RATE_SOURCE, STATUS = range(8)

    rate_edited = Signal(list, object)  # [invoice keys], rate id or None
    payment_edited = Signal(str, object)  # invoice key, date

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[InvoiceRow] = []
        self.rules: RuleSet | None = None
        self.language = "cs"

    def set_report(self, report: InvoiceReport | None, rules: RuleSet | None, language: str) -> None:
        self.beginResetModel()
        self._rows = list(report.rows) if report else []
        self.rules = rules
        self.language = language
        self.endResetModel()

    def row(self, index: _Index) -> InvoiceRow:
        return self._rows[index.row()]

    def retranslate(self) -> None:
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.columnCount() - 1)
        if self._rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._rows) - 1, self.STATUS))

    def rowCount(self, parent: _Index = _ROOT) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: _Index = _ROOT) -> int:
        return 0 if parent.isValid() else 8

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal or role != Qt.ItemDataRole.DisplayRole:
            return None
        return [
            self.tr("Number"),
            self.tr("Customer"),
            self.tr("Issued"),
            self.tr("Paid"),
            self.tr("Amount"),
            self.tr("Flat rate"),
            self.tr("Rate from"),
            self.tr("Status"),
        ][section]

    def flags(self, index: _Index):
        base = super().flags(index)
        row = self._rows[index.row()]
        if row.counted and index.column() in (self.PAID, self.RATE):
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def data(self, index: _Index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = self._rows[index.row()], index.column()
        inv = row.invoice

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(row, col)
        if role == Qt.ItemDataRole.EditRole:
            if col == self.PAID:
                paid = row.payment_date or date.today()
                return QDate(paid.year, paid.month, paid.day)
            if col == self.RATE:
                return row.rate_id
        if role == RATE_ROLE:
            return row.rate_id
        if role == SORT_ROLE:
            return {
                self.NUMBER: inv.number or "",
                self.CUSTOMER: (inv.customer_name or inv.customer_ico or "").casefold(),
                self.ISSUED: inv.issue_date.isoformat() if inv.issue_date else "",
                self.PAID: row.payment_date.isoformat() if row.payment_date else "",
                self.AMOUNT: float(inv.signed_amount or 0),
                self.RATE: row.rate_id or "",
                self.RATE_SOURCE: row.rate_source or "",
                self.STATUS: int(row.severity) if row.severity is not None else -1,
            }[col]
        if role == Qt.ItemDataRole.TextAlignmentRole and col == self.AMOUNT:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.DecorationRole and col == self.STATUS and row.severity is not None:
            return severity_icon(row.severity)
        if role == Qt.ItemDataRole.ToolTipRole:
            tips = [str(inv.source)]
            tips += [f"• {issue_text(i)}" for i in row.issues]
            if col == self.PAID and not row.payment_confirmed and row.payment_date:
                tips.append(self.tr("Estimated from the due date - double-click to enter the actual date."))
            return "\n".join(tips)
        if role == Qt.ItemDataRole.FontRole and col == self.PAID and not row.payment_confirmed:
            font = QFont()
            font.setItalic(True)  # italic = estimated, not confirmed
            return font
        return None

    def _display(self, row: InvoiceRow, col: int):
        inv = row.invoice
        if col == self.NUMBER:
            prefix = {DocType.CREDIT_NOTE: "↩ ", DocType.ADVANCE: "⧗ "}.get(inv.doc_type, "")
            return prefix + (inv.number or inv.source.name)
        if col == self.CUSTOMER:
            return inv.customer_name or inv.customer_ico or "—"
        if col == self.ISSUED:
            return _cz(inv.issue_date)
        if col == self.PAID:
            return _cz(row.payment_date)
        if col == self.AMOUNT:
            amount = inv.signed_amount
            return format_czk(amount, 2) if amount is not None else "?"
        if col == self.RATE:
            return rate_label(self.rules, row.rate_id, self.language) if row.counted else ""
        if col == self.RATE_SOURCE:
            return {
                RateSource.MANUAL: self.tr("manual"),
                RateSource.GROUP: self.tr("group (auto)"),
                RateSource.ARES: self.tr("ARES"),
            }.get(row.rate_source or "", "")
        if col == self.STATUS:
            if not row.issued_by_me:
                return self.tr("Received")
            if not row.counted:
                return self.tr("Not counted")
            if inv.needs_review:
                origin = self.tr("OCR") if inv.origin is Origin.OCR else self.tr("PDF text")
                return self.tr("To check ({0})").format(origin)
            if row.severity is None or row.severity == Severity.INFO:
                return self.tr("OK")
            return self.tr("Check")
        return None

    def setData(self, index: _Index, value, role=Qt.ItemDataRole.EditRole) -> bool:
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        row = self._rows[index.row()]
        if index.column() == self.RATE:
            self.rate_edited.emit([row.invoice.key], value)
            return True
        if index.column() == self.PAID and isinstance(value, QDate):
            self.payment_edited.emit(row.invoice.key, date(value.year(), value.month(), value.day()))
            return True
        return False


class GroupsModel(QAbstractTableModel):
    LABEL, COUNT, AMOUNT, RATE = range(4)

    group_rate_edited = Signal(str, object)  # group id, rate id or None

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._groups: list[tuple[InvoiceGroup, str | None, bool]] = []  # group, rate, mixed?
        self.rules: RuleSet | None = None
        self.language = "cs"

    def set_report(self, report: InvoiceReport | None, rules: RuleSet | None, language: str) -> None:
        self.beginResetModel()
        self._groups = []
        rates = {r.invoice.key: r.rate_id for r in report.rows} if report else {}
        for group in report.groups if report else []:
            member_rates = {rates.get(i.key) for i in group.invoices}
            mixed = len(member_rates) > 1
            self._groups.append((group, None if mixed else next(iter(member_rates)), mixed))
        self.rules = rules
        self.language = language
        self.endResetModel()

    def group(self, index: _Index) -> InvoiceGroup:
        return self._groups[index.row()][0]

    def retranslate(self) -> None:
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.columnCount() - 1)

    def rowCount(self, parent: _Index = _ROOT) -> int:
        return 0 if parent.isValid() else len(self._groups)

    def columnCount(self, parent: _Index = _ROOT) -> int:
        return 0 if parent.isValid() else 4

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal or role != Qt.ItemDataRole.DisplayRole:
            return None
        return [
            self.tr("Group of similar invoices"),
            self.tr("Count"),
            self.tr("Amount"),
            self.tr("Flat rate"),
        ][section]

    def flags(self, index: _Index):
        base = super().flags(index)
        return base | Qt.ItemFlag.ItemIsEditable if index.column() == self.RATE else base

    def data(self, index: _Index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        group, rate_id, mixed = self._groups[index.row()]
        col = index.column()
        total = sum((i.signed_amount or 0 for i in group.invoices), 0)
        if role == Qt.ItemDataRole.DisplayRole:
            if col == self.LABEL:
                # Two lines (who / typical words) fit the narrow side panel
                # better than one long, elided line.
                who = group.customer_name or group.customer_ico or "?"
                return f"{who}\n{', '.join(group.top_words)}" if group.top_words else who
            if col == self.COUNT:
                return len(group.invoices)
            if col == self.AMOUNT:
                return format_czk(total)
            if col == self.RATE:
                return self.tr("mixed") if mixed else rate_label(self.rules, rate_id, self.language)
        if role in (Qt.ItemDataRole.EditRole, RATE_ROLE) and col == self.RATE:
            return rate_id
        if role == Qt.ItemDataRole.DecorationRole and col == self.LABEL and rate_id is None and not mixed:
            return severity_icon(Severity.ERROR)  # a group still waiting for a rate
        if role == Qt.ItemDataRole.TextAlignmentRole and col in (self.COUNT, self.AMOUNT):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            members = [f"{i.number or i.source.name}: {i.description_text[:80]}" for i in group.invoices]
            return "\n".join([group.label, "", *members])
        return None

    def setData(self, index: _Index, value, role=Qt.ItemDataRole.EditRole) -> bool:
        if role == Qt.ItemDataRole.EditRole and index.isValid() and index.column() == self.RATE:
            self.group_rate_edited.emit(self._groups[index.row()][0].id, value)
            return True
        return False


def _cz(value: date | None) -> str:
    return f"{value.day}.{value.month}.{value.year}" if value else "—"
