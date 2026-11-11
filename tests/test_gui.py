"""GUI smoke tests (pytest-qt). Run headless with QT_QPA_PLATFORM=offscreen."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal
from importlib import resources
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QSettings, Qt  # noqa: E402

from commission_tax_calc.core.issues import Issue, IssueCode, Severity  # noqa: E402
from commission_tax_calc.core.loader import LoadResult  # noqa: E402
from commission_tax_calc.core.money import format_czk  # noqa: E402
from commission_tax_calc.core.parser import parse_text  # noqa: E402
from commission_tax_calc.core.rules import RulesRepository  # noqa: E402
from commission_tax_calc.gui.i18n import LanguageManager  # noqa: E402
from commission_tax_calc.gui.issue_texts import _templates, issue_text  # noqa: E402
from commission_tax_calc.gui.main_window import MainWindow  # noqa: E402
from commission_tax_calc.gui.workers import LoadWorker, start_in_thread  # noqa: E402
from factory import Spec, make_text  # noqa: E402


@pytest.fixture
def window(qtbot, qapp, tmp_path):
    # Isolate QSettings in a temp INI file - never touch the real registry.
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    QCoreApplication.setOrganizationName("test")
    QCoreApplication.setApplicationName("commission-tax-calc-tests")
    QSettings().setValue("rules/update_policy", "never")
    i18n = LanguageManager(qapp)
    i18n.set_language("en")
    win = MainWindow(i18n, RulesRepository(None))
    qtbot.addWidget(win)
    yield win
    i18n.set_language("en")


def load(win: MainWindow, statements, failures=()):
    # Bypass the worker thread: tests the computing/display path directly.
    win._loaded = LoadResult(list(statements), list(failures))
    win._refresh_years()


def make(name, **changes):
    return parse_text(make_text(Spec(**changes)), source=Path(name))


def test_shows_totals(window):
    load(
        window,
        [
            make(
                "a.pdf", start=date(2026, 1, 1), end=date(2026, 1, 14), rows=[("A", "1", "P", "X, a.s.", 741)]
            ),
            make(
                "b.pdf",
                start=date(2026, 1, 15),
                end=date(2026, 1, 31),
                rows=[("B", "2", "P", "X, a.s.", 259)],
            ),
        ],
    )
    assert window.year_combo.currentData() == 2026
    assert window.total_value.text() == format_czk(Decimal(1000))
    assert window.expenses_value.text() == format_czk(Decimal(400))
    assert window.base_value.text() == format_czk(Decimal(600))
    assert window.statements_model.rowCount() == 2
    assert window.tax_model.rowCount() == 1


def test_failures_are_listed(window):
    failure = Issue(IssueCode.PARSE_FAILED, Severity.ERROR, Path("broken.pdf"), {"reason": "x"})
    load(window, [make("a.pdf")], [failure])
    assert window.statements_model.rowCount() == 2
    texts = [window.issues_table.item(r, 2).text() for r in range(window.issues_table.rowCount())]
    assert any("Could not read" in t for t in texts)


def test_runtime_language_switch(window, qapp):
    load(window, [make("a.pdf")])
    window._i18n.set_language("cs")
    qapp.processEvents()
    assert window.open_action.text() == "Otevřít složku…"
    assert window.tax_box.title() == "Souhrn pro daňové přiznání"
    assert window.statements_model.headerData(0, Qt.Orientation.Horizontal) == "Soubor"
    window._i18n.set_language("en")
    qapp.processEvents()
    assert window.open_action.text() == "Open folder…"


def test_unknown_activity_asks_user(window, monkeypatch):
    from commission_tax_calc.gui import main_window

    monkeypatch.setattr(main_window.QInputDialog, "getItem", staticmethod(lambda *a, **k: (a[3][1], True)))
    load(window, [make("a.pdf", activities=[("Tajemná činnost", (), 1000)])])
    assert window._overrides == {"Tajemná činnost": "trades"}
    assert window.expenses_value.text() == format_czk(Decimal(600))


def test_rules_dialog_opens(window, qtbot):
    window.open_rules_dialog()
    dialog = window._rules_dialog
    assert dialog is not None
    assert dialog.rates_table.rowCount() == 4
    assert "e-sbirka.cz" in dialog.sources_label.text()
    dialog.close()


def test_load_worker_runs_in_thread(qtbot, window, tmp_path):
    folder = tmp_path / "statements"
    folder.mkdir()
    (folder / "not-really.pdf").write_text("garbage")
    worker = LoadWorker(folder)
    with qtbot.waitSignal(worker.finished, timeout=10000) as blocker:
        thread = start_in_thread(worker, window)
    result = blocker.args[0]
    assert result.statements == []
    assert result.failures[0].code is IssueCode.PARSE_FAILED
    thread.wait(2000)


def test_every_issue_code_has_translatable_text():
    assert set(_templates()) == set(IssueCode)
    issue = Issue(IssueCode.GAP, Severity.WARNING, None, {"start": "1.1.", "end": "2.1."})
    assert "1.1." in issue_text(issue)


def test_czech_translation_is_complete():
    ts = resources.files("commission_tax_calc") / "translations" / "app_cs.ts"
    root = ET.fromstring(ts.read_text("utf-8"))
    unfinished = [
        m.findtext("source")
        for m in root.iter("message")
        if m.find("translation").get("type") == "unfinished"
    ]
    assert unfinished == []
    assert (resources.files("commission_tax_calc") / "translations" / "app_cs.qm").is_file()
