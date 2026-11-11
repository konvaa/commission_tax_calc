"""Runtime language switching the Qt way.

How Qt localization works (and how it differs from a plain-Python dict):

* Source strings are written in English inside ``self.tr("…")`` /
  ``QCoreApplication.translate("Context", "…")``.
* ``pyside6-lupdate`` scans the sources and writes ``translations/app_cs.ts``
  (XML), which is translated (by hand or in Qt Linguist).
* ``pyside6-lrelease`` compiles it to a binary ``app_cs.qm``.
* At runtime a ``QTranslator`` loaded with the ``.qm`` is installed on the
  application. Installing/removing it makes Qt send a ``LanguageChange`` event
  to every widget, which re-runs ``retranslate_ui()``.

English is the source language, so switching to English simply removes the
translator. ``qtbase_cs`` is loaded as well so standard buttons of
``QMessageBox``/``QDialogButtonBox`` ("Yes", "Cancel") are translated too.
"""

from __future__ import annotations

from importlib import resources

from PySide6.QtCore import QLibraryInfo, QLocale, QObject, QSettings, QTranslator, Signal
from PySide6.QtWidgets import QApplication

LANGUAGES = {"cs": "Čeština", "en": "English"}
_SETTINGS_KEY = "ui/language"


class LanguageManager(QObject):
    language_changed = Signal(str)

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._app = app
        self._translators: list[QTranslator] = []
        self.language = "en"

    def initial_language(self) -> str:
        saved = QSettings().value(_SETTINGS_KEY, "", type=str)
        if saved in LANGUAGES:
            return saved
        # First start: follow the OS. A Czech Windows gets Czech UI.
        return "cs" if QLocale.system().language() == QLocale.Language.Czech else "en"

    def set_language(self, code: str) -> None:
        if code not in LANGUAGES:
            code = "en"
        for translator in self._translators:
            self._app.removeTranslator(translator)
        self._translators.clear()

        if code != "en":
            app_qm = resources.files("commission_tax_calc") / "translations" / f"app_{code}.qm"
            with resources.as_file(app_qm) as path:
                self._install(str(path))
            qt_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
            self._install(f"qtbase_{code}", qt_dir)

        self.language = code
        QSettings().setValue(_SETTINGS_KEY, code)
        self.language_changed.emit(code)

    def _install(self, name: str, directory: str = "") -> None:
        translator = QTranslator(self)
        # A missing .qm is not fatal - the UI just stays in English.
        if translator.load(name, directory) if directory else translator.load(name):
            self._app.installTranslator(translator)
            self._translators.append(translator)
