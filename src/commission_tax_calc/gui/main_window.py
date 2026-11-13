"""Main application window.

The window holds *state* (folder, loaded documents, selected year/mode,
manual overrides, the invoice store) and wires widgets to core functions. All calculations are
delegated to ``core``; the window only decides *when* to recompute.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import shiboken6
from PySide6.QtCore import QEvent, QSettings, QSortFilterProxyModel, Qt, QThread, QTimer
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QSplitter,
    QStyle,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..core.aggregator import YearMode, YearReport, available_years, build_report
from ..core.ares import AresInfo, suggested_rate_ids
from ..core.grouping import profile_from_group, similar
from ..core.ico import is_valid
from ..core.invoice_report import InvoiceReport, build_invoice_report, detect_my_ico, invoice_years
from ..core.invoice_store import InvoiceStore
from ..core.issues import Issue, IssueCode, Severity
from ..core.loader import LoadResult
from ..core.money import format_czk
from ..core.paths import user_data_dir
from ..core.rules import RuleSet, RulesRepository, UpdateResult, text
from ..core.tax import UNASSIGNED_INVOICES_LABEL, TaxSummary, compute
from .i18n import LANGUAGES, LanguageManager
from .invoices_panel import InvoicesPanel
from .issue_texts import issue_text, severity_text
from .review_dialog import ReviewDialog
from .rules_dialog import RulesDialog
from .table_models import SORT_ROLE, StatementsModel, TaxModel, severity_icon
from .workers import AresWorker, LoadWorker, RulesUpdateWorker, start_in_thread

_KEY_FOLDER = "ui/last_folder"
_KEY_MODE = "ui/year_mode"
_KEY_YEAR = "ui/year"
_KEY_GEOMETRY = "ui/geometry"
_KEY_SPLITTER = "ui/splitter"
_KEY_OVERRIDES = "rules/overrides"
_KEY_POLICY = "rules/update_policy"
_KEY_ARES_POLICY = "ares/policy"


class MainWindow(QMainWindow):
    def __init__(
        self, i18n: LanguageManager, repository: RulesRepository, store: InvoiceStore | None = None
    ) -> None:
        super().__init__()
        self._i18n = i18n
        self._repo = repository
        self._settings = QSettings()

        self._folder: Path | None = None
        self._loaded: LoadResult | None = None
        self._report: YearReport | None = None
        self._tax: TaxSummary | None = None
        self._rules: RuleSet | None = None
        self._rules_exact = True
        self._overrides: dict[str, str] = self._read_overrides()
        self._asked_categories: set[str] = set()
        # References to running threads/workers; see workers.start_in_thread.
        self._jobs: list[object] = []
        self._rules_dialog: RulesDialog | None = None
        self._loading_worker: LoadWorker | None = None
        self._updating = False
        self._update_interactive = False
        # Invoice decisions (own IČO, rates, payment dates, corrections) live in
        # a JSON file shared with the CLI; see core/invoice_store.py.
        self._store = store or InvoiceStore.load(user_data_dir() / "invoices.json")
        self._invoice_report: InvoiceReport | None = None
        self._ares_running = False
        self._ares_interactive = False
        self._ico_asked = False

        self._build_ui()
        self.setAcceptDrops(True)
        self.retranslate_ui()
        i18n.language_changed.connect(self._on_language_changed)

        geometry = self._settings.value(_KEY_GEOMETRY)
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1180, 760)
        splitter_state = self._settings.value(_KEY_SPLITTER)
        if splitter_state is not None:
            self.splitter.restoreState(splitter_state)

        last = self._settings.value(_KEY_FOLDER, "", type=str)
        if last and Path(last).is_dir():
            # Deferred so the window is painted before the first parse starts.
            QTimer.singleShot(0, lambda: self.load_folder(Path(last)))

    # ================================================================ UI ==
    def _build_ui(self) -> None:
        style = self.style()
        self.open_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon), "", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.triggered.connect(self.choose_folder)
        self.reload_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "", self)
        self.reload_action.setShortcut("F5")
        self.reload_action.triggered.connect(self.reload)
        self.rules_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), "", self
        )
        self.rules_action.triggered.connect(self.open_rules_dialog)

        self.year_label = QLabel()
        self.year_combo = QComboBox()
        self.year_combo.setMinimumWidth(80)
        self.year_combo.currentIndexChanged.connect(self._recompute)
        self.mode_label = QLabel()
        self.mode_combo = QComboBox()
        # Store the plain string value: PySide converts str-based enums to str
        # when they round-trip through QVariant, so convert back in _mode().
        self.mode_combo.addItem("", YearMode.BY_PERIOD.value)
        self.mode_combo.addItem("", YearMode.BY_PAYOUT.value)
        saved_mode = self._settings.value(_KEY_MODE, YearMode.BY_PERIOD.value, type=str)
        self.mode_combo.setCurrentIndex(1 if saved_mode == YearMode.BY_PAYOUT.value else 0)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.language_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.language_combo.addItem(name, code)
        self.language_combo.setCurrentIndex(self.language_combo.findData(self._i18n.language))
        self.language_combo.currentIndexChanged.connect(
            lambda: self._i18n.set_language(self.language_combo.currentData())
        )

        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.reload_action)
        toolbar.addSeparator()
        toolbar.addWidget(self.year_label)
        toolbar.addWidget(self.year_combo)
        toolbar.addWidget(self.mode_label)
        toolbar.addWidget(self.mode_combo)
        toolbar.addSeparator()
        toolbar.addAction(self.rules_action)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        toolbar.addWidget(self.language_combo)
        self.addToolBar(toolbar)
        self.toolbar = toolbar

        # -- statements --------------------------------------------------
        self.folder_label = QLabel()
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.statements_model = StatementsModel(self)
        self.statements_proxy = QSortFilterProxyModel(self)
        self.statements_proxy.setSourceModel(self.statements_model)
        self.statements_proxy.setSortRole(SORT_ROLE)
        self.statements_view = QTableView()
        self.statements_view.setModel(self.statements_proxy)
        self.statements_view.setSortingEnabled(True)
        self.statements_view.sortByColumn(StatementsModel.PERIOD, Qt.SortOrder.AscendingOrder)
        self.statements_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.statements_view.setAlternatingRowColors(True)
        self.statements_view.verticalHeader().setVisible(False)
        header = self.statements_view.horizontalHeader()
        header.setSectionResizeMode(StatementsModel.FILE, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 6):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        self.statements_box = QWidget()
        statements_layout = QVBoxLayout(self.statements_box)
        statements_layout.setContentsMargins(4, 4, 4, 4)
        statements_layout.addWidget(self.statements_view)

        # -- invoices ----------------------------------------------------
        self.invoices_panel = InvoicesPanel()
        self.invoices_panel.change_ico_requested.connect(lambda: self._ask_my_ico(force=True))
        self.invoices_panel.ares_requested.connect(lambda: self._start_ares(interactive=True))
        self.invoices_panel.review_requested.connect(self._review_invoice)
        self.invoices_panel.rates_requested.connect(self._set_rates)
        self.invoices_panel.payments_confirm_requested.connect(self._confirm_payments)
        self.invoices_panel.model.rate_edited.connect(self._set_rates)
        self.invoices_panel.model.payment_edited.connect(self._set_payment)
        self.invoices_panel.groups_model.group_rate_edited.connect(self._set_group_rate)

        # Statements and invoices are two tabs over one shared summary: both
        # feed the same tax computation.
        self.tabs = QTabWidget()
        self.tabs.addTab(self.statements_box, "")
        self.tabs.addTab(self.invoices_panel, "")
        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(self.folder_label)
        top_layout.addWidget(self.tabs)

        # -- tax summary -------------------------------------------------
        self.tax_model = TaxModel(self)
        self.tax_view = QTableView()
        self.tax_view.setModel(self.tax_model)
        self.tax_view.verticalHeader().setVisible(False)
        self.tax_view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        tax_header = self.tax_view.horizontalHeader()
        tax_header.setSectionResizeMode(TaxModel.CATEGORY, QHeaderView.ResizeMode.Stretch)
        for col in (TaxModel.RATE, TaxModel.INCOME, TaxModel.EXPENSES, TaxModel.BASE):
            tax_header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        big = QFont()
        big.setPointSize(big.pointSize() + 6)
        big.setBold(True)
        bold = QFont()
        bold.setBold(True)
        self.total_value = QLabel("—")
        self.total_value.setFont(big)
        self.total_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.income_value, self.expenses_value, self.base_value = QLabel("—"), QLabel("—"), QLabel("—")
        for label in (self.income_value, self.expenses_value, self.base_value):
            label.setFont(bold)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.invoices_value = QLabel("—")
        self.invoices_value.setFont(bold)
        self.invoices_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.invoices_caption = QLabel()
        self.total_caption = QLabel()
        self.income_caption, self.expenses_caption, self.base_caption = QLabel(), QLabel(), QLabel()
        totals = QFormLayout()
        totals.addRow(self.total_caption, self.total_value)
        totals.addRow(self.invoices_caption, self.invoices_value)
        totals.addRow(self.income_caption, self.income_value)
        totals.addRow(self.expenses_caption, self.expenses_value)
        totals.addRow(self.base_caption, self.base_value)

        self.disclaimer = QLabel()
        self.disclaimer.setWordWrap(True)
        self.disclaimer.setStyleSheet("color: palette(mid);")

        self.tax_box = QGroupBox()
        tax_layout = QVBoxLayout(self.tax_box)
        tax_layout.addLayout(totals)
        tax_layout.addWidget(self.tax_view)
        tax_layout.addWidget(self.disclaimer)

        # -- findings ----------------------------------------------------
        self.issues_table = QTableWidget(0, 3)
        self.issues_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.issues_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.issues_table.verticalHeader().setVisible(False)
        self.issues_table.setWordWrap(True)
        issues_header = self.issues_table.horizontalHeader()
        issues_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        issues_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        issues_header.setStretchLastSection(True)
        self.show_info_check = QCheckBox()
        self.show_info_check.setChecked(True)
        self.show_info_check.toggled.connect(self._fill_issues)
        self.issues_box = QGroupBox()
        issues_layout = QVBoxLayout(self.issues_box)
        issues_layout.addWidget(self.issues_table)
        issues_layout.addWidget(self.show_info_check)

        bottom = QSplitter(Qt.Orientation.Horizontal)
        bottom.addWidget(self.tax_box)
        bottom.addWidget(self.issues_box)
        bottom.setSizes([560, 600])

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(top)
        self.splitter.addWidget(bottom)
        self.splitter.setSizes([330, 400])
        self.setCentralWidget(self.splitter)

        # -- status bar --------------------------------------------------
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setVisible(False)
        self.rules_status = QLabel()
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().addPermanentWidget(self.rules_status)

    # =========================================================== i18n ==
    def changeEvent(self, event: QEvent) -> None:
        # Qt sends LanguageChange to every widget when a translator is
        # installed or removed - this is the hook for runtime switching.
        if event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.tr("Commission Tax Calc") + f" {__version__}")
        self.open_action.setText(self.tr("Open folder…"))
        self.open_action.setToolTip(
            self.tr("Choose the folder with commission statements and invoices (Ctrl+O)")
        )
        self.reload_action.setText(self.tr("Reload"))
        self.rules_action.setText(self.tr("Rules…"))
        self.rules_action.setToolTip(self.tr("Show flat-rate expense rules and their sources"))
        self.year_label.setText(" " + self.tr("Tax year:") + " ")
        self.mode_label.setText("  " + self.tr("Assign by:") + " ")
        self.mode_combo.setItemText(0, self.tr("statement period"))
        self.mode_combo.setItemText(1, self.tr("expected payout (cash basis)"))
        self.mode_combo.setToolTip(
            self.tr(
                "Statements contain only the period, not the payout date.\n"
                "'Expected payout' moves a statement ending on 31 December to the next year,\n"
                "because it is paid out in January. Check with your accountant which applies.\n"
                "Invoices are always assigned by their payment date."
            )
        )
        self.total_caption.setText(self.tr("Commission total (Provize celkem):"))
        self.invoices_caption.setText(self.tr("Issued invoices (by payment date):"))
        self.income_caption.setText(self.tr("Income § 7:"))
        self.expenses_caption.setText(self.tr("Flat-rate expenses:"))
        self.base_caption.setText(self.tr("Partial tax base § 7:"))
        self.tax_box.setTitle(self.tr("Tax return summary"))
        self.disclaimer.setText(
            self.tr(
                "Informative calculation, not tax advice. Verify the rates against the current "
                "law (Rules… → Open current law online) or with a tax advisor."
            )
        )
        self.issues_table.setHorizontalHeaderLabels(
            [self.tr("Severity"), self.tr("Document"), self.tr("Message")]
        )
        self.show_info_check.setText(self.tr("Show informational notes"))
        self.statements_model.retranslate()
        self._update_views()

    def _on_language_changed(self, code: str) -> None:
        self.tax_model.retranslate(code)
        if self._rules_dialog is not None:
            self._rules_dialog.set_language(code)
        self._update_views()

    # ======================================================= loading ==
    def choose_folder(self) -> None:
        start = str(self._folder) if self._folder else ""
        folder = QFileDialog.getExistingDirectory(self, self.tr("Folder with statements and invoices"), start)
        if folder:
            self.load_folder(Path(folder))

    def reload(self) -> None:
        if self._folder:
            self.load_folder(self._folder)

    def load_folder(self, folder: Path) -> None:
        if self._is_loading():
            return
        self._folder = folder
        self._settings.setValue(_KEY_FOLDER, str(folder))
        self._set_busy(True)
        worker = LoadWorker(folder, self._store.my_ico)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_loaded)
        self._loading_worker = worker
        self._start_job(worker)

    def _is_loading(self) -> bool:
        return self._loading_worker is not None

    def _start_job(self, worker) -> None:
        # Signals from a worker thread are connected only to *bound methods of
        # this window* (a QObject living in the GUI thread). Qt then queues the
        # call into the GUI thread. A lambda has no thread affinity, so it could
        # run in the worker thread and touch widgets from there - a classic
        # source of random crashes.
        thread = start_in_thread(worker, self)
        self._jobs = [job for job in self._jobs if shiboken6.isValid(job)] + [worker, thread]

    def _on_progress(self, done: int, total: int, name: str) -> None:
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)
        self.statusBar().showMessage(self.tr("Reading {0} ({1}/{2})").format(name, done, total))

    def _on_loaded(self, result: LoadResult) -> None:
        self._loading_worker = None
        self._loaded = result
        self._set_busy(False)
        self.statusBar().showMessage(
            self.tr("Read {0} statement(s) and {1} invoice(s), {2} problem(s).").format(
                len(result.statements), len(result.invoices), len(result.failures)
            ),
            8000,
        )
        self._refresh_years()
        if result.invoices:
            # Deferred: let the window repaint with the results before asking.
            QTimer.singleShot(0, self._after_invoices_loaded)

    def _set_busy(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        self.progress.setValue(0)
        for action in (self.open_action, self.reload_action):
            action.setEnabled(not busy)

    # ===================================================== computing ==
    def _mode(self) -> YearMode:
        return YearMode(self.mode_combo.currentData())

    def _on_mode_changed(self) -> None:
        self._settings.setValue(_KEY_MODE, self._mode().value)
        self._refresh_years()

    def _refresh_years(self) -> None:
        statements = self._loaded.statements if self._loaded else []
        invoices = self._loaded.invoices if self._loaded else []
        years = sorted(set(available_years(statements, self._mode())) | invoice_years(invoices, self._store))
        previous = self.year_combo.currentData() or self._settings.value(_KEY_YEAR, 0, type=int)
        self.year_combo.blockSignals(True)  # avoid recomputing for every addItem
        self.year_combo.clear()
        for year in years:
            self.year_combo.addItem(str(year), year)
        index = self.year_combo.findData(previous)
        self.year_combo.setCurrentIndex(index if index >= 0 else len(years) - 1)
        self.year_combo.blockSignals(False)
        self._recompute()

    def _recompute(self) -> None:
        year = self.year_combo.currentData()
        self._report = self._tax = self._rules = self._invoice_report = None
        if self._loaded is not None and year is not None:
            self._settings.setValue(_KEY_YEAR, year)
            self._report = build_report(self._loaded.statements, year, self._mode())
            self._rules, self._rules_exact = self._repo.get(year)
            ares_rates = self._ares_rate_ids(year)
            self._invoice_report = build_invoice_report(self._loaded.invoices, year, self._store, ares_rates)
            if self._rules is not None:
                self._tax = self._compute_tax()
                if self._tax.unmapped and self._ask_unknown_activities(self._tax, self._rules):
                    self._tax = self._compute_tax()
        self._update_views()

    def _compute_tax(self) -> TaxSummary:
        invoices = self._invoice_report
        return compute(
            self._report.activity_totals,
            self._rules,
            self._overrides,
            invoices.rate_income if invoices else None,
            invoices.unassigned if invoices else 0,
        )

    def _ares_rate_ids(self, year: int) -> set[str] | None:
        info = self._store.ares.get(self._store.my_ico or "")
        rules, _ = self._repo.get(year)
        if info is None or rules is None:
            return None
        return suggested_rate_ids(info, rules, date(year, 12, 31))

    def _ask_unknown_activities(self, tax: TaxSummary, rules: RuleSet) -> bool:
        """Ask once per session for each activity type the rules don't know.

        Returns True if at least one choice was made. Deferring the question
        to the user (instead of guessing 60 %) is deliberate: a wrong guess
        would silently change the tax base.
        """
        lang = self._i18n.language
        choices = [f"{r.percent} % – {text(r.name, lang)}" for r in rules.rates]
        changed = False
        for category, amount in tax.unmapped.items():
            # Unassigned invoices are handled in the Invoices tab, not here.
            if category in self._asked_categories or category == UNASSIGNED_INVOICES_LABEL:
                continue
            self._asked_categories.add(category)
            choice, ok = QInputDialog.getItem(
                self,
                self.tr("Unknown activity type"),
                self.tr(
                    "The statements contain an activity type the rules do not know:\n\n"
                    "„{0}“ ({1})\n\nWhich flat-rate category does it belong to?"
                ).format(category, format_czk(amount)),
                choices,
                0,
                False,
            )
            if ok:
                self._overrides[category] = rules.rates[choices.index(choice)].id
                changed = True
        if changed:
            self._write_overrides()
        return changed

    # ======================================================== views ==
    def _update_views(self) -> None:
        failures = self._loaded.failures if self._loaded else []
        self.statements_model.set_data(self._report, failures)
        self.tax_model.set_summary(self._tax, self._i18n.language)

        if self._folder is None:
            self.folder_label.setText(
                self.tr("No folder selected – click “Open folder…” or drop a folder here.")
            )
        else:
            self.folder_label.setText(self.tr("Folder: {0}").format(self._folder))

        counted = len(self._report.counted) if self._report else 0
        shown = len(self._report.rows) if self._report else 0
        self.tabs.setTabText(0, self.tr("Commission statements ({0} of {1})").format(counted, shown))
        invoices = self._invoice_report
        self.tabs.setTabText(
            1,
            self.tr("Invoices ({0} of {1})").format(
                len(invoices.counted) if invoices else 0, len(invoices.rows) if invoices else 0
            ),
        )
        self.invoices_panel.set_data(
            invoices, self._rules, self._i18n.language, self._store.my_ico, self._ares_text()
        )

        if self._report is not None:
            self.total_value.setText(format_czk(self._report.total))
        else:
            self.total_value.setText("—")
        self.invoices_value.setText(format_czk(invoices.total, 2) if invoices else "—")
        if self._tax is not None:
            self.income_value.setText(format_czk(self._tax.income))
            self.expenses_value.setText(format_czk(self._tax.expenses))
            self.base_value.setText(format_czk(self._tax.partial_base))
        else:
            for label in (self.income_value, self.expenses_value, self.base_value):
                label.setText("—")

        if self._rules is not None:
            origin = self.tr("bundled") if self._rules.origin == "bundled" else self.tr("downloaded")
            status = self.tr("Rules {0}, revision {1} ({2})").format(
                self._rules.tax_year, self._rules.revision, origin
            )
            if not self._rules_exact:
                status = "⚠ " + status
            self.rules_status.setText(status)
        else:
            self.rules_status.setText(self.tr("Rules: —"))
        self._fill_issues()

    def _current_issues(self) -> list[Issue]:
        issues: list[Issue] = list(self._loaded.failures) if self._loaded else []
        if self._report is not None:
            issues += self._report.all_issues()
        if self._invoice_report is not None:
            issues += self._invoice_report.all_issues()
        if self._tax is not None:
            issues += self._tax.issues
        if self._rules is not None and not self._rules_exact and self._report is not None:
            issues.append(
                Issue(
                    IssueCode.NO_RULES_FOR_YEAR,
                    Severity.WARNING,
                    None,
                    {"year": self._report.year, "used_year": self._rules.tax_year},
                )
            )
        return sorted(issues, key=lambda i: -i.severity)

    def _fill_issues(self) -> None:
        issues = self._current_issues()
        if not self.show_info_check.isChecked():
            issues = [i for i in issues if i.severity > Severity.INFO]
        # Show the statement *period* rather than the long file name - it is
        # shorter and it is what the user thinks in ("the 2nd half of Nov").
        periods = {st.source: str(st.period) for st in (self._loaded.statements if self._loaded else [])}
        periods.update(
            {
                inv.source: inv.number or inv.source.name
                for inv in (self._loaded.invoices if self._loaded else [])
            }
        )
        self.issues_table.setRowCount(len(issues))
        for row, issue in enumerate(issues):
            severity = QTableWidgetItem(severity_icon(issue.severity), severity_text(issue.severity))
            self.issues_table.setItem(row, 0, severity)
            where = "—"
            if issue.source is not None:
                where = periods.get(issue.source, issue.source.name)
            where_item = QTableWidgetItem(where)
            if issue.source is not None:
                where_item.setToolTip(str(issue.source))
            self.issues_table.setItem(row, 1, where_item)
            message = QTableWidgetItem(issue_text(issue))
            message.setToolTip(issue_text(issue))
            self.issues_table.setItem(row, 2, message)
        self.issues_table.resizeColumnToContents(1)
        self.issues_table.resizeRowsToContents()
        problems = sum(1 for i in self._current_issues() if i.severity > Severity.INFO)
        self.issues_box.setTitle(self.tr("Findings ({0} to check)").format(problems))

    # ===================================================== invoices ==
    def _after_invoices_loaded(self) -> None:
        if not self._store.my_ico and not self._ico_asked:
            self._ask_my_ico()
        if self._store.my_ico and self._store.my_ico not in self._store.ares:
            self._maybe_start_ares()

    def _ask_my_ico(self, force: bool = False) -> None:
        """Confirm the user's own IČO; invoices issued by others are ignored.

        The detected value is only a proposal - the user confirms or edits it.
        """
        self._ico_asked = True
        invoices = self._loaded.invoices if self._loaded else []
        proposal = self._store.my_ico or detect_my_ico(invoices) or ""
        name = next((i.supplier_name for i in invoices if i.supplier_ico == proposal and i.supplier_name), "")
        prompt = self.tr("Your IČO (as the supplier on your issued invoices):")
        if name and not force:
            prompt = self.tr("Found invoices issued by {0}. Is this your IČO?").format(name)
        while True:
            value, ok = QInputDialog.getText(self, self.tr("My IČO"), prompt, text=proposal)
            if not ok:
                return
            value = value.strip()
            if is_valid(value):
                break
            QMessageBox.warning(self, self.tr("My IČO"), self.tr("{0} is not a valid IČO.").format(value))
            proposal = value
        self._store.my_ico = value
        self._save_store()
        self._refresh_years()
        if value not in self._store.ares:
            self._maybe_start_ares()

    def _maybe_start_ares(self) -> None:
        policy = self._settings.value(_KEY_ARES_POLICY, "ask", type=str)
        if policy == "never":
            return
        if policy == "ask":
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle(self.tr("Trades from ARES"))
            box.setText(self.tr("Look up your trades in the public register ARES?"))
            box.setInformativeText(
                self.tr(
                    "From your trades the app can suggest the flat-rate percentage of your invoices. "
                    "Only your IČO is sent to ares.gov.cz."
                )
            )
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            remember = QCheckBox(self.tr("Remember my choice"))
            box.setCheckBox(remember)
            yes = box.exec() == QMessageBox.StandardButton.Yes
            if remember.isChecked():
                self._settings.setValue(_KEY_ARES_POLICY, "always" if yes else "never")
            if not yes:
                return
        self._start_ares(interactive=False)

    def _start_ares(self, interactive: bool) -> None:
        if self._ares_running or not self._store.my_ico:
            return
        self._ares_running = True
        self._ares_interactive = interactive
        self.statusBar().showMessage(self.tr("Looking up trades in ARES…"))
        worker = AresWorker(self._store.my_ico)
        worker.finished.connect(self._on_ares_done)
        worker.failed.connect(self._on_ares_failed)
        self._start_job(worker)

    def _on_ares_done(self, info: AresInfo) -> None:
        self._ares_running = False
        self._store.ares[info.ico] = info
        self._save_store()
        self.statusBar().showMessage(self.tr("ARES: {0} trade(s) found.").format(len(info.trades)), 8000)
        self._recompute()

    def _on_ares_failed(self, error: str) -> None:
        self._ares_running = False
        message = self.tr("ARES lookup failed: {0}").format(error)
        self.statusBar().showMessage(message, 10000)
        if self._ares_interactive:
            QMessageBox.warning(self, self.tr("Trades from ARES"), message)

    def _ares_text(self) -> str:
        info = self._store.ares.get(self._store.my_ico or "")
        if info is None:
            return self.tr("ARES: not looked up yet")
        year = self.year_combo.currentData() or date.today().year
        rates = self._ares_rate_ids(year) or set()
        trades = info.active_trades(date(year, 12, 31))
        names = "; ".join(t.subject for t in trades) or self.tr("no active trade")
        if len(rates) == 1 and self._rules is not None:
            rate = self._rules.rate(next(iter(rates)))
            summary = self.tr("all lead to {0} % – applied automatically").format(
                rate.percent if rate else "?"
            )
        elif len(rates) > 1:
            summary = self.tr("different rates – assign groups below")
        else:
            summary = self.tr("no suggestion")
        return self.tr("ARES ({0}): {1} → {2}").format(info.fetched.strftime("%d.%m.%Y"), names, summary)

    def _set_rates(self, keys: list, rate_id) -> None:
        for key in keys:
            if rate_id:
                self._store.manual_rates[key] = rate_id
            else:
                self._store.manual_rates.pop(key, None)
        self._save_store()
        self._recompute()

    def _set_group_rate(self, group_id: str, rate_id) -> None:
        """Set the rate for all invoices of a group and remember the group.

        The current invoices get the rate as a manual choice (the user just
        made it). The remembered profile is for *future* invoices - those are
        flagged "group (auto)" so the user notices them.
        """
        report = self._invoice_report
        group = next((g for g in report.groups if g.id == group_id), None) if report else None
        if group is None:
            return
        for invoice in group.invoices:
            if rate_id:
                self._store.manual_rates[invoice.key] = rate_id
            else:
                self._store.manual_rates.pop(invoice.key, None)
        profile = profile_from_group(group, rate_id) if rate_id else None
        # Replace profiles describing the same kind of invoices, so changing a
        # group's rate does not leave a contradicting old profile behind.
        self._store.profiles = [
            p
            for p in self._store.profiles
            if not similar(p.tokens, p.customer_ico, group.token_union, group.customer_ico)
        ] + ([profile] if profile else [])
        self._save_store()
        self._recompute()

    def _set_payment(self, key: str, paid: date) -> None:
        self._store.payment_dates[key] = paid
        self._save_store()
        self._refresh_years()

    def _confirm_payments(self, keys: list) -> None:
        rows = {r.invoice.key: r for r in (self._invoice_report.rows if self._invoice_report else [])}
        for key in keys:
            row = rows.get(key)
            if row and row.payment_date:
                self._store.payment_dates[key] = row.payment_date
        self._save_store()
        self._refresh_years()

    def _review_invoice(self, key: str) -> None:
        rows = {r.invoice.key: r for r in (self._invoice_report.rows if self._invoice_report else [])}
        row = rows.get(key)
        if row is None:
            return
        dialog = ReviewDialog(row.invoice, self)
        if dialog.exec() == ReviewDialog.DialogCode.Accepted:
            self._store.set_correction(row.invoice, dialog.values())
            self._save_store()
            self._refresh_years()

    def _save_store(self) -> None:
        try:
            self._store.save()
        except OSError as exc:
            QMessageBox.warning(self, self.windowTitle(), self.tr("Could not save settings: {0}").format(exc))

    # ======================================================== rules ==
    def open_rules_dialog(self) -> None:
        if self._rules_dialog is None:
            dialog = RulesDialog(
                self._repo,
                self.year_combo.currentData(),
                self._i18n.language,
                self._overrides,
                self._settings.value(_KEY_POLICY, "ask", type=str),
                self,
            )
            dialog.update_requested.connect(lambda: self.start_rules_update(interactive=True))
            dialog.overrides_cleared.connect(self._clear_overrides)
            dialog.policy_changed.connect(lambda p: self._settings.setValue(_KEY_POLICY, p))
            dialog.finished.connect(lambda _: setattr(self, "_rules_dialog", None))
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            self._rules_dialog = dialog
        self._rules_dialog.show()
        self._rules_dialog.raise_()

    def _clear_overrides(self) -> None:
        self._overrides.clear()
        self._asked_categories.clear()
        self._write_overrides()
        self._recompute()

    def maybe_check_rules_on_startup(self) -> None:
        policy = self._settings.value(_KEY_POLICY, "ask", type=str)
        if policy == "never":
            return
        if policy == "ask":
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle(self.tr("Flat-rate expense rules"))
            box.setText(self.tr("Check online for updated flat-rate expense rules?"))
            box.setInformativeText(
                self.tr(
                    "The app downloads a small rules file from the project's GitHub repository. "
                    "No personal data is sent."
                )
            )
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            remember = QCheckBox(self.tr("Remember my choice"))
            box.setCheckBox(remember)
            answer = box.exec()
            yes = answer == QMessageBox.StandardButton.Yes
            if remember.isChecked():
                self._settings.setValue(_KEY_POLICY, "always" if yes else "never")
            if not yes:
                return
        self.start_rules_update(interactive=False)

    def start_rules_update(self, interactive: bool) -> None:
        if self._updating:
            return
        self._updating = True
        self._update_interactive = interactive
        if self._rules_dialog:
            self._rules_dialog.set_update_running(True)
        self.statusBar().showMessage(self.tr("Checking for rule updates…"))
        worker = RulesUpdateWorker(self._repo)
        worker.finished.connect(self._on_rules_updated)
        worker.failed.connect(self._on_rules_failed)
        self._start_job(worker)

    def _rules_update_done(self) -> None:
        self._updating = False
        if self._rules_dialog:
            self._rules_dialog.set_update_running(False)
            self._rules_dialog.refresh()

    def _on_rules_updated(self, result: UpdateResult) -> None:
        interactive = self._update_interactive
        self._rules_update_done()
        if result.updated_years:
            message = self.tr("Rules updated for: {0}").format(", ".join(map(str, result.updated_years)))
        else:
            message = self.tr("Rules are up to date.")
        self.statusBar().showMessage(message, 8000)
        if interactive:
            QMessageBox.information(self, self.tr("Flat-rate expense rules"), message)
        self._recompute()

    def _on_rules_failed(self, error: str) -> None:
        interactive = self._update_interactive
        self._rules_update_done()
        message = self.tr("Could not update rules, using the saved ones. ({0})").format(error)
        self.statusBar().showMessage(message, 10000)
        if interactive:
            QMessageBox.warning(self, self.tr("Flat-rate expense rules"), message)

    # ================================================== persistence ==
    def _read_overrides(self) -> dict[str, str]:
        raw = self._settings.value(_KEY_OVERRIDES, "{}", type=str)
        try:
            data = json.loads(raw)
        except ValueError:
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    def _write_overrides(self) -> None:
        self._settings.setValue(_KEY_OVERRIDES, json.dumps(self._overrides, ensure_ascii=False))

    # ================================================== drag & drop ==
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).is_dir():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        self.load_folder(Path(event.mimeData().urls()[0].toLocalFile()))

    # ======================================================== close ==
    def closeEvent(self, event) -> None:
        self._settings.setValue(_KEY_GEOMETRY, self.saveGeometry())
        self._settings.setValue(_KEY_SPLITTER, self.splitter.saveState())
        # Let running threads finish so Qt does not destroy them mid-run.
        for job in self._jobs:
            if isinstance(job, QThread) and shiboken6.isValid(job):
                job.quit()
                job.wait(3000)
        super().closeEvent(event)


__all__ = ["MainWindow"]
