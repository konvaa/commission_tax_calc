"""Dialog showing the loaded flat-rate rules, sources and manual choices."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..core.money import format_czk
from ..core.rules import RulesRepository, text

UPDATE_POLICIES = ("ask", "always", "never")


class RulesDialog(QDialog):
    update_requested = Signal()
    overrides_cleared = Signal()
    policy_changed = Signal(str)

    def __init__(
        self,
        repository: RulesRepository,
        year: int | None,
        language: str,
        overrides: dict[str, str],
        policy: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._repo = repository
        self._language = language
        self._overrides = dict(overrides)
        self.resize(900, 640)

        self.year_combo = QComboBox()
        self.year_combo.currentIndexChanged.connect(self._show_rules)
        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        self.note_label = QLabel()
        self.note_label.setWordWrap(True)

        self.rates_table = self._make_table(5)
        self.mapping_table = self._make_table(2)
        self.overrides_table = self._make_table(2)

        self.sources_label = QLabel()
        self.sources_label.setOpenExternalLinks(True)  # links open in the browser
        self.sources_label.setWordWrap(True)

        self.open_online_button = QPushButton()
        self.open_online_button.clicked.connect(self._open_online)
        self.update_button = QPushButton()
        self.update_button.clicked.connect(self.update_requested)
        self.clear_overrides_button = QPushButton()
        self.clear_overrides_button.clicked.connect(self._clear_overrides)
        self.policy_combo = QComboBox()
        self.policy_combo.addItems(["", "", ""])
        self.policy_combo.setCurrentIndex(UPDATE_POLICIES.index(policy) if policy in UPDATE_POLICIES else 0)
        self.policy_combo.currentIndexChanged.connect(lambda i: self.policy_changed.emit(UPDATE_POLICIES[i]))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        top = QFormLayout()
        self.year_label = QLabel()
        top.addRow(self.year_label, self.year_combo)

        self.rates_box = QGroupBox()
        QVBoxLayout(self.rates_box).addWidget(self.rates_table)
        self.mapping_box = QGroupBox()
        QVBoxLayout(self.mapping_box).addWidget(self.mapping_table)
        self.overrides_box = QGroupBox()
        overrides_layout = QVBoxLayout(self.overrides_box)
        overrides_layout.addWidget(self.overrides_table)
        overrides_layout.addWidget(self.clear_overrides_button)
        self.sources_box = QGroupBox()
        sources_layout = QVBoxLayout(self.sources_box)
        sources_layout.addWidget(self.sources_label)
        sources_layout.addWidget(self.open_online_button)

        lower = QHBoxLayout()
        lower.addWidget(self.mapping_box, 3)
        lower.addWidget(self.overrides_box, 2)

        update_row = QHBoxLayout()
        self.policy_label = QLabel()
        update_row.addWidget(self.policy_label)
        update_row.addWidget(self.policy_combo)
        update_row.addStretch()
        update_row.addWidget(self.update_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.info_label)
        layout.addWidget(self.note_label)
        layout.addWidget(self.rates_box, 3)
        layout.addLayout(lower, 2)
        layout.addWidget(self.sources_box)
        layout.addLayout(update_row)
        layout.addWidget(buttons)

        self.retranslate_ui()
        self.refresh(select_year=year)

    @staticmethod
    def _make_table(columns: int) -> QTableWidget:
        table = QTableWidget(0, columns)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setWordWrap(True)
        return table

    # -- public -----------------------------------------------------------
    def refresh(self, select_year: int | None = None) -> None:
        """Re-read the repository (e.g. after an update)."""
        current = select_year or self.year_combo.currentData()
        self.year_combo.blockSignals(True)
        self.year_combo.clear()
        for y in self._repo.years:
            self.year_combo.addItem(str(y), y)
        index = self.year_combo.findData(current)
        self.year_combo.setCurrentIndex(index if index >= 0 else self.year_combo.count() - 1)
        self.year_combo.blockSignals(False)
        self._show_rules()

    def set_language(self, language: str) -> None:
        self._language = language
        self._show_rules()

    def set_update_running(self, running: bool) -> None:
        self.update_button.setEnabled(not running)

    # -- i18n -------------------------------------------------------------
    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.tr("Flat-rate expense rules"))
        self.year_label.setText(self.tr("Tax year:"))
        self.rates_box.setTitle(self.tr("Rates (§ 7 odst. 7 ZDP)"))
        self.mapping_box.setTitle(self.tr("How statement activity types map to rates"))
        self.overrides_box.setTitle(self.tr("Your manual choices"))
        self.sources_box.setTitle(self.tr("Sources"))
        self.open_online_button.setText(self.tr("Open current law online"))
        self.update_button.setText(self.tr("Check for updates now"))
        self.clear_overrides_button.setText(self.tr("Clear manual choices"))
        self.policy_label.setText(self.tr("Check for rule updates at startup:"))
        for i, label in enumerate((self.tr("Ask"), self.tr("Always"), self.tr("Never"))):
            self.policy_combo.setItemText(i, label)
        self.rates_table.setHorizontalHeaderLabels(
            [
                self.tr("Rate"),
                self.tr("Max. expenses"),
                self.tr("Category"),
                self.tr("Provision"),
                self.tr("Examples"),
            ]
        )
        self.mapping_table.setHorizontalHeaderLabels([self.tr("Statement text contains"), self.tr("Rate")])
        self.overrides_table.setHorizontalHeaderLabels([self.tr("Activity type"), self.tr("Rate")])
        self._show_rules()

    # -- internals --------------------------------------------------------
    def _show_rules(self) -> None:
        year = self.year_combo.currentData()
        rules, _ = self._repo.get(year) if year is not None else (None, False)
        if rules is None:
            self.info_label.setText(self.tr("No rules available."))
            return
        lang = self._language
        origin = self.tr("bundled with the app") if rules.origin == "bundled" else self.tr("downloaded")
        self.info_label.setText(
            self.tr("Revision {0}, updated {1}, source: {2}. Income cap per rate: {3}.").format(
                rules.revision, rules.updated, origin, format_czk(rules.income_cap)
            )
        )
        self.note_label.setText(f"<i>{text(rules.note, lang)}</i>")

        self.rates_table.setRowCount(len(rules.rates))
        for row, rate in enumerate(rules.rates):
            cells = [
                f"{rate.percent} %",
                format_czk(rate.max_expenses),
                text(rate.name, lang),
                rate.legal_ref,
                ", ".join(rate.examples.get(lang) or rate.examples.get("cs", ())),
            ]
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setToolTip(text(rate.description, lang))
                self.rates_table.setItem(row, col, item)
        self.rates_table.resizeColumnsToContents()
        self.rates_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.rates_table.resizeRowsToContents()

        self.mapping_table.setRowCount(len(rules.mappings))
        for row, mapping in enumerate(rules.mappings):
            rate = rules.rate(mapping.rate_id)
            self.mapping_table.setItem(row, 0, QTableWidgetItem(f"„{mapping.match}“"))
            self.mapping_table.setItem(
                row, 1, QTableWidgetItem(f"{rate.percent} % – {text(rate.name, lang)}" if rate else "?")
            )
        self.mapping_table.resizeColumnToContents(0)

        self.overrides_table.setRowCount(len(self._overrides))
        for row, (category, rate_id) in enumerate(sorted(self._overrides.items())):
            rate = rules.rate(rate_id)
            self.overrides_table.setItem(row, 0, QTableWidgetItem(category))
            self.overrides_table.setItem(row, 1, QTableWidgetItem(f"{rate.percent} %" if rate else rate_id))
        self.clear_overrides_button.setEnabled(bool(self._overrides))

        links = "<br>".join(f'<a href="{s.url}">{text(s.label, lang)}</a>' for s in rules.sources)
        self.sources_label.setText(links)
        self.open_online_button.setEnabled(bool(rules.sources))

    def _open_online(self) -> None:
        year = self.year_combo.currentData()
        rules, _ = self._repo.get(year)
        if rules and rules.sources:
            QDesktopServices.openUrl(QUrl(rules.sources[0].url))

    def _clear_overrides(self) -> None:
        self._overrides.clear()
        self.overrides_cleared.emit()
        self._show_rules()
