"""The "Invoices" tab: invoice table, groups of similar invoices, own IČO and ARES.

The panel only displays and collects user intents (signals). The main window
owns the store and recomputes - the same split as in the rest of the GUI.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSortFilterProxyModel, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..core.invoice_report import InvoiceReport
from ..core.rules import RuleSet, text
from .invoice_table_models import GroupsModel, InvoicesModel, RateDelegate
from .table_models import SORT_ROLE


class InvoicesPanel(QWidget):
    change_ico_requested = Signal()
    ares_requested = Signal()
    review_requested = Signal(str)  # invoice key
    rates_requested = Signal(list, object)  # [keys], rate id or None
    payments_confirm_requested = Signal(list)  # [keys] - accept the shown date

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rules: RuleSet | None = None
        self._language = "cs"

        # -- header: own IČO and ARES ----------------------------------------
        self.ico_label = QLabel()
        self.ico_button = QPushButton()
        self.ico_button.clicked.connect(self.change_ico_requested)
        self.ares_label = QLabel()
        self.ares_label.setWordWrap(True)
        self.ares_button = QPushButton()
        self.ares_button.clicked.connect(self.ares_requested)
        header = QHBoxLayout()
        header.addWidget(self.ico_label)
        header.addWidget(self.ico_button)
        header.addSpacing(24)
        header.addWidget(self.ares_label, 1)
        header.addWidget(self.ares_button)

        # -- invoices table ----------------------------------------------------
        self.model = InvoicesModel(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(SORT_ROLE)
        self.delegate = RateDelegate(self)
        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setItemDelegateForColumn(InvoicesModel.RATE, self.delegate)
        self.view.setSortingEnabled(True)
        self.view.sortByColumn(InvoicesModel.ISSUED, Qt.SortOrder.AscendingOrder)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # Editing starts on double-click or by typing; a double-click on a
        # non-editable cell opens the review dialog instead.
        self.view.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.view.doubleClicked.connect(self._double_clicked)
        self.view.setAlternatingRowColors(True)
        self.view.verticalHeader().setVisible(False)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._context_menu)
        header_view = self.view.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(InvoicesModel.CUSTOMER, QHeaderView.ResizeMode.Stretch)

        # -- groups table ------------------------------------------------------
        self.groups_model = GroupsModel(self)
        self.groups_view = QTableView()
        self.groups_view.setModel(self.groups_model)
        self.groups_delegate = RateDelegate(self)
        self.groups_view.setItemDelegateForColumn(GroupsModel.RATE, self.groups_delegate)
        self.groups_view.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.groups_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.groups_view.verticalHeader().setVisible(False)
        self.groups_view.selectionModel().selectionChanged.connect(self._highlight_group)
        groups_header = self.groups_view.horizontalHeader()
        groups_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        groups_header.setSectionResizeMode(GroupsModel.LABEL, QHeaderView.ResizeMode.Stretch)
        self.groups_hint = QLabel()
        self.groups_hint.setWordWrap(True)
        self.groups_box = QGroupBox()
        groups_layout = QVBoxLayout(self.groups_box)
        groups_layout.addWidget(self.groups_hint)
        groups_layout.addWidget(self.groups_view)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.view)
        splitter.addWidget(self.groups_box)
        splitter.setSizes([700, 420])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(header)
        layout.addWidget(splitter)
        self.retranslate_ui()

    # -- data ----------------------------------------------------------------
    def set_data(
        self,
        report: InvoiceReport | None,
        rules: RuleSet | None,
        language: str,
        my_ico: str | None,
        ares_text: str,
    ) -> None:
        self._rules, self._language = rules, language
        for delegate in (self.delegate, self.groups_delegate):
            delegate.rules, delegate.language = rules, language
        self.model.set_report(report, rules, language)
        self.groups_model.set_report(report, rules, language)
        self.groups_view.resizeRowsToContents()
        self.ico_label.setText(self.tr("My IČO: {0}").format(my_ico or "—"))
        self.ares_label.setText(ares_text)
        self.ares_button.setEnabled(bool(my_ico))

    # -- i18n ----------------------------------------------------------------
    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self) -> None:
        self.ico_button.setText(self.tr("Change…"))
        self.ares_button.setText(self.tr("Look up in ARES"))
        self.groups_box.setTitle(self.tr("Groups of similar invoices"))
        self.groups_hint.setText(
            self.tr(
                "Invoices for the same customer with similar item texts are grouped. "
                "Double-click the rate of a group to set it for all its invoices; "
                "new similar invoices will get it automatically."
            )
        )
        self.model.retranslate()
        self.groups_model.retranslate()

    # -- interaction ---------------------------------------------------------
    def _selected_keys(self) -> list[str]:
        rows = {self.proxy.mapToSource(i).row() for i in self.view.selectionModel().selectedRows()}
        return [self.model.row(self.model.index(r, 0)).invoice.key for r in sorted(rows)]

    def _double_clicked(self, proxy_index) -> None:
        index = self.proxy.mapToSource(proxy_index)
        if not (self.model.flags(index) & Qt.ItemFlag.ItemIsEditable):
            self.review_requested.emit(self.model.row(index).invoice.key)

    def _context_menu(self, position) -> None:
        keys = self._selected_keys()
        if not keys:
            return
        menu = QMenu(self)
        rate_menu = menu.addMenu(self.tr("Set flat rate ({0} invoices)").format(len(keys)))
        for rate in self._rules.rates if self._rules else ():
            action = rate_menu.addAction(f"{rate.percent} % – {text(rate.name, self._language)}")
            action.triggered.connect(lambda _=False, r=rate.id: self.rates_requested.emit(keys, r))
        menu.addAction(self.tr("Clear manual rate"), lambda: self.rates_requested.emit(keys, None))
        menu.addSeparator()
        menu.addAction(
            self.tr("Confirm payment date as shown"), lambda: self.payments_confirm_requested.emit(keys)
        )
        if len(keys) == 1:
            menu.addAction(self.tr("Check and edit values…"), lambda: self.review_requested.emit(keys[0]))
        menu.exec(self.view.viewport().mapToGlobal(position))

    def _highlight_group(self) -> None:
        """Selecting a group selects its invoices in the table."""
        selected = self.groups_view.selectionModel().selectedRows()
        if not selected:
            return
        group = self.groups_model.group(selected[0])
        keys = {i.key for i in group.invoices}
        selection = self.view.selectionModel()
        selection.clearSelection()
        for row in range(self.model.rowCount()):
            if self.model.row(self.model.index(row, 0)).invoice.key in keys:
                proxy_index = self.proxy.mapFromSource(self.model.index(row, 0))
                selection.select(
                    proxy_index,
                    selection.SelectionFlag.Select | selection.SelectionFlag.Rows,
                )
