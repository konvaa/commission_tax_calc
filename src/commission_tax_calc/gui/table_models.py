"""Qt Model/View models for the statements and tax-summary tables.

Why ``QAbstractTableModel`` instead of filling a ``QTableWidget`` cell by cell:
the model keeps the *data* (our core objects) and answers questions about it
per role - text for ``DisplayRole``, a number for ``SORT_ROLE``, an icon for
``DecorationRole``. The view only renders. Sorting then works on real values
(dates, Decimals) via ``QSortFilterProxyModel`` instead of on formatted
strings, where "9 000 Kč" would sort after "10 000 Kč".
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtWidgets import QApplication, QStyle

from ..core.aggregator import YearReport
from ..core.issues import Issue, Severity
from ..core.money import format_czk
from ..core.rules import text
from ..core.tax import INVOICES_LABEL, UNASSIGNED_INVOICES_LABEL, TaxSummary
from .issue_texts import issue_text, severity_text

SORT_ROLE = Qt.ItemDataRole.UserRole + 1
_Index = QModelIndex | QPersistentModelIndex
# Invalid index = "the root" of a flat table. A module-level constant instead
# of ``QModelIndex()`` in each signature avoids a call in default arguments.
_ROOT = QModelIndex()


def severity_icon(severity: Severity):
    style = QApplication.style()
    pixmap = {
        Severity.INFO: QStyle.StandardPixmap.SP_MessageBoxInformation,
        Severity.WARNING: QStyle.StandardPixmap.SP_MessageBoxWarning,
        Severity.ERROR: QStyle.StandardPixmap.SP_MessageBoxCritical,
    }[severity]
    return style.standardIcon(pixmap)


@dataclass(frozen=True)
class _StatementRow:
    file: str
    period: str
    period_key: object
    year: int | None
    total: Decimal | None
    payout: Decimal | None
    counted: bool
    issues: tuple[Issue, ...]

    @property
    def severity(self) -> Severity | None:
        return max((i.severity for i in self.issues), default=None)


class StatementsModel(QAbstractTableModel):
    FILE, PERIOD, YEAR, TOTAL, PAYOUT, STATUS = range(6)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[_StatementRow] = []

    def set_data(self, report: YearReport | None, failures: list[Issue]) -> None:
        # begin/endResetModel tells attached views that everything changed;
        # cheaper and simpler than per-row insert signals for a full reload.
        self.beginResetModel()
        rows = []
        for row in report.rows if report else []:
            st = row.statement
            rows.append(
                _StatementRow(
                    st.source.name,
                    str(st.period),
                    st.period,
                    row.tax_year,
                    st.summary.total,
                    st.summary.payout,
                    row.counted,
                    row.issues,
                )
            )
        for issue in failures:
            name = issue.source.name if issue.source else "?"
            rows.append(_StatementRow(name, "—", None, None, None, None, False, (issue,)))
        self._rows = rows
        self.endResetModel()

    def retranslate(self) -> None:
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.columnCount() - 1)
        if self._rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._rows) - 1, self.STATUS))

    # -- QAbstractTableModel API ------------------------------------------
    def rowCount(self, parent: _Index = _ROOT) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: _Index = _ROOT) -> int:
        return 0 if parent.isValid() else 6

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal or role != Qt.ItemDataRole.DisplayRole:
            return None
        return [
            self.tr("File"),
            self.tr("Period"),
            self.tr("Tax year"),
            self.tr("Commission total"),
            self.tr("Payout"),
            self.tr("Status"),
        ][section]

    def data(self, index: _Index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = self._rows[index.row()], index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(row, col)
        if role == SORT_ROLE:
            return {
                self.FILE: row.file.casefold(),
                self.PERIOD: row.period_key.start.isoformat() if row.period_key else "",
                self.YEAR: row.year or 0,
                self.TOTAL: float(row.total or 0),  # float is fine for *sorting*
                self.PAYOUT: float(row.payout or 0),
                self.STATUS: int(row.severity) if row.severity is not None else -1,
            }[col]
        if role == Qt.ItemDataRole.TextAlignmentRole and col in (self.TOTAL, self.PAYOUT):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.DecorationRole and col == self.STATUS and row.severity is not None:
            return severity_icon(row.severity)
        if role == Qt.ItemDataRole.ToolTipRole and row.issues:
            return "\n".join(f"• {issue_text(i)}" for i in row.issues)
        if role == Qt.ItemDataRole.FontRole and not row.counted and row.total is not None:
            font = QApplication.font()
            font.setStrikeOut(True)  # duplicates are visibly "not counted"
            return font
        return None

    def _display(self, row: _StatementRow, col: int):
        if col == self.FILE:
            return row.file
        if col == self.PERIOD:
            return row.period
        if col == self.YEAR:
            return str(row.year) if row.year else "—"
        if col == self.TOTAL:
            return format_czk(row.total) if row.total is not None else "—"
        if col == self.PAYOUT:
            if row.payout is None:
                return "—"
            # Show haléře only when there are some ("1 128,47 Kč" vs "44 997 Kč").
            return format_czk(row.payout, 0 if row.payout == row.payout.to_integral() else 2)
        if col == self.STATUS:
            if row.total is None:
                return self.tr("Not read")
            if not row.counted:
                return self.tr("Not counted")
            if row.severity is None or row.severity == Severity.INFO:
                return self.tr("OK")
            return severity_text(row.severity)
        return None


class TaxModel(QAbstractTableModel):
    """One row per flat-rate category, as entered in the tax return."""

    RATE, CATEGORY, INCOME, EXPENSES, BASE = range(5)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._summary: TaxSummary | None = None
        self.language = "cs"

    def set_summary(self, summary: TaxSummary | None, language: str) -> None:
        self.beginResetModel()
        self._summary = summary
        self.language = language
        self.endResetModel()

    def retranslate(self, language: str) -> None:
        self.set_summary(self._summary, language)

    def _lines(self):
        if not self._summary:
            return []
        rows = [
            (
                f"{line.rate.percent} %",
                text(line.rate.name, self.language),
                line.income,
                line.expenses,
                line.partial_base,
                line,
            )
            for line in self._summary.lines
        ]
        rows += [
            ("?", self._activity_label(category), amount, None, None, None)
            for category, amount in self._summary.unmapped.items()
        ]
        return rows

    def _activity_label(self, category: str) -> str:
        # Invoice pseudo-categories come from the core in Czech; translate
        # them here. Statement headings are quoted from the PDF as they are.
        if category == INVOICES_LABEL:
            return self.tr("Issued invoices")
        if category == UNASSIGNED_INVOICES_LABEL:
            return self.tr("Invoices without a flat rate")
        return category

    def rowCount(self, parent: _Index = _ROOT) -> int:
        return 0 if parent.isValid() else len(self._lines())

    def columnCount(self, parent: _Index = _ROOT) -> int:
        return 0 if parent.isValid() else 5

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal or role != Qt.ItemDataRole.DisplayRole:
            return None
        return [
            self.tr("Rate"),
            self.tr("Category"),
            self.tr("Income"),
            self.tr("Expenses"),
            self.tr("Partial tax base"),
        ][section]

    def data(self, index: _Index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        rate, category, income, expenses, base, line = self._lines()[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            value = [rate, category, income, expenses, base][col]
            if isinstance(value, Decimal):
                return format_czk(value)
            return value if value is not None else "—"
        if role == Qt.ItemDataRole.TextAlignmentRole and col >= self.INCOME:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            if line is None:
                return self.tr("Unknown activity type - choose a rate in the dialog.")
            tip = [text(line.rate.description, self.language), line.rate.legal_ref]
            labels = "; ".join(self._activity_label(a) for a in line.activities)
            tip.append(self.tr("Sources of income:") + " " + labels)
            if line.capped:
                tip.append(self.tr("Income exceeds the cap; expenses are limited."))
            return "\n".join(t for t in tip if t)
        if role == Qt.ItemDataRole.DecorationRole and col == self.RATE and line is None:
            return severity_icon(Severity.ERROR)
        return None
