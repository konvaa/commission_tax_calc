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

from commission_tax_calc.core.invoice_store import InvoiceStore  # noqa: E402
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
    QSettings().setValue("ares/policy", "never")
    i18n = LanguageManager(qapp)
    i18n.set_language("en")
    win = MainWindow(i18n, RulesRepository(None), InvoiceStore(tmp_path / "invoices.json"))
    qtbot.addWidget(win)
    yield win
    i18n.set_language("en")


def load(win: MainWindow, statements, failures=()):
    # Bypass the worker thread: tests the computing/display path directly.
    win._loaded = LoadResult(statements=list(statements), failures=list(failures))
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


# ----------------------------------------------------------------- invoices ---


def own_invoice(number, text="Montáž elektroinstalace", amount=10000, **changes):
    from commission_tax_calc.core.isdoc import parse_isdoc
    from factory import InvoiceSpec, make_isdoc

    spec = InvoiceSpec(number=number, lines=[(text, amount)], **changes)
    return parse_isdoc(make_isdoc(spec), Path(f"{number}.pdf"))


def load_invoices(win: MainWindow, invoices):
    from factory import SUPPLIER_ICO

    win._store.my_ico = SUPPLIER_ICO
    win._loaded = LoadResult(invoices=list(invoices))
    win._refresh_years()


def test_invoices_tab_and_manual_rate(window):
    from commission_tax_calc.gui.invoice_table_models import InvoicesModel

    load_invoices(window, [own_invoice("2030001"), own_invoice("2030002", "Pronájem lešení", 5000)])
    model = window.invoices_panel.model
    assert model.rowCount() == 2
    assert window.base_value.text() == format_czk(Decimal(15000))  # no rate yet -> no expenses
    model.setData(model.index(0, InvoicesModel.RATE), "trades", Qt.ItemDataRole.EditRole)
    assert list(window._store.manual_rates.values()) == ["trades"]
    assert window.expenses_value.text() == format_czk(Decimal(6000))
    assert (window._store.path).is_file()  # decisions are persisted immediately


def test_group_rate_applies_to_all_members_and_is_remembered(window):
    from commission_tax_calc.gui.invoice_table_models import GroupsModel

    load_invoices(
        window,
        [
            own_invoice("2030001", "Montáž elektroinstalace, Lužná"),
            own_invoice("2030002", "Montáž elektroinstalace, Lhota"),
        ],
    )
    groups = window.invoices_panel.groups_model
    assert groups.rowCount() == 1
    groups.setData(groups.index(0, GroupsModel.RATE), "crafts_agriculture", Qt.ItemDataRole.EditRole)
    assert set(window._store.manual_rates.values()) == {"crafts_agriculture"}
    assert len(window._store.profiles) == 1
    assert window.expenses_value.text() == format_czk(Decimal(16000))

    # A new similar invoice is assigned automatically and flagged.
    load_invoices(window, [own_invoice("2030003", "Montáž elektroinstalace, Frenštát")])
    row = window._invoice_report.rows[0]
    assert (row.rate_id, row.rate_source) == ("crafts_agriculture", "group")


def test_payment_date_edit_moves_invoice_to_other_year(window):
    from PySide6.QtCore import QDate

    from commission_tax_calc.gui.invoice_table_models import InvoicesModel

    load_invoices(window, [own_invoice("2030001")])
    model = window.invoices_panel.model
    model.setData(model.index(0, InvoicesModel.PAID), QDate(2031, 1, 10), Qt.ItemDataRole.EditRole)
    assert window.year_combo.findData(2031) >= 0
    assert window.year_combo.findData(2030) == -1


def test_review_dialog_returns_corrected_values(qtbot):
    from commission_tax_calc.gui.review_dialog import ReviewDialog

    invoice = own_invoice("2030001")
    dialog = ReviewDialog(invoice)
    qtbot.addWidget(dialog)
    dialog.amount.setText("12 345,60")
    dialog.number.setText("2030009")
    values = dialog.values()
    assert values["amount"] == Decimal("12345.60")
    assert values["number"] == "2030009"
    assert values["supplier_ico"] == invoice.supplier_ico
