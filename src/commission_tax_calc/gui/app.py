"""GUI entry point: ``commission-tax-calc`` or ``python -m commission_tax_calc``."""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ..core.paths import rules_cache_dir
from ..core.rules import RulesRepository
from .i18n import LanguageManager
from .main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    # Organization + application name define where QSettings stores data
    # (on Windows: HKCU\Software\konvaa\CommissionTaxCalc).
    app.setOrganizationName("konvaa")
    app.setApplicationName("CommissionTaxCalc")
    app.setStyle("Fusion")  # identical look on Windows, Linux and in CI screenshots

    i18n = LanguageManager(app)
    i18n.set_language(i18n.initial_language())

    window = MainWindow(i18n, RulesRepository(rules_cache_dir()))
    window.show()
    # Ask about rule updates only after the window is visible, so the
    # question has a parent window instead of popping up out of nowhere.
    QTimer.singleShot(300, window.maybe_check_rules_on_startup)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
