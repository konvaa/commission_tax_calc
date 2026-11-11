"""Main application window.

The window holds *state* (folder, loaded statements, selected year/mode,
manual overrides) and wires widgets to core functions. All calculations are
delegated to ``core``; the window only decides *when* to recompute.
"""

from __future__ import annotations

import json
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
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..core.aggregator import YearMode, YearReport, available_years, build_report
from ..core.issues import Issue, IssueCode, Severity
from ..core.loader import LoadResult
from ..core.money import format_czk
from ..core.rules import RuleSet, RulesRepository, UpdateResult, text
from ..core.tax import TaxSummary, compute
from .i18n import LANGUAGES, LanguageManager
from .issue_texts import issue_text, severity_text
from .rules_dialog import RulesDialog
from .table_models import SORT_ROLE, StatementsModel, TaxModel, severity_icon
from .workers import LoadWorker, RulesUpdateWorker, start_in_thread

_KEY_FOLDER = "ui/last_folder"
_KEY_MODE = "ui/year_mode"
_KEY_YEAR = "ui/year"
_KEY_GEOMETRY = "ui/geometry"
_KEY_SPLITTER = "ui/splitter"
_KEY_OVERRIDES = "rules/overrides"
_KEY_POLICY = "rules/update_policy"


class MainWindow(QMainWindow):
    def __init__(self, i18n: LanguageManager, repository: RulesRepository) -> None:
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

        self.statements_box = QGroupBox()
        statements_layout = QVBoxLayout(self.statements_box)
        statements_layout.addWidget(self.folder_label)
        statements_layout.addWidget(self.statements_view)

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
        self.total_caption = QLabel()
        self.income_caption, self.expenses_caption, self.base_caption = QLabel(), QLabel(), QLabel()
        totals = QFormLayout()
        totals.addRow(self.total_caption, self.total_value)
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
        self.splitter.addWidget(self.statements_box)
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
        self.open_action.setToolTip(self.tr("Choose the folder with downloaded statements (Ctrl+O)"))
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
                "because it is paid out in January. Check with your accountant which applies."
            )
        )
        self.total_caption.setText(self.tr("Commission total (Provize celkem):"))
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
            [self.tr("Severity"), self.tr("Statement"), self.tr("Message")]
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
        folder = QFileDialog.getExistingDirectory(self, self.tr("Folder with statements"), start)
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
        worker = LoadWorker(folder)
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
            self.tr("Read {0} statement(s), {1} failed.").format(
                len(result.statements), len(result.failures)
            ),
            8000,
        )
        self._refresh_years()

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
        years = available_years(statements, self._mode())
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
        self._report = self._tax = self._rules = None
        if self._loaded is not None and year is not None:
            self._settings.setValue(_KEY_YEAR, year)
            self._report = build_report(self._loaded.statements, year, self._mode())
            self._rules, self._rules_exact = self._repo.get(year)
            if self._rules is not None:
                self._tax = compute(self._report.activity_totals, self._rules, self._overrides)
                if self._tax.unmapped and self._ask_unknown_activities(self._tax, self._rules):
                    self._tax = compute(self._report.activity_totals, self._rules, self._overrides)
        self._update_views()

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
            if category in self._asked_categories:
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
        self.statements_box.setTitle(self.tr("Statements ({0} counted of {1})").format(counted, shown))

        if self._report is not None:
            self.total_value.setText(format_czk(self._report.total))
        else:
            self.total_value.setText("—")
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
