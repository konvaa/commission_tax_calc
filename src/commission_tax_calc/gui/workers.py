"""Background work off the GUI thread: reading documents, rules updates, ARES.

Why threads: pdfplumber needs ~0.1-0.3 s per statement, OCR of a scanned
invoice about a second per page. Doing that in the GUI thread would freeze
the window (no repaint, "Not responding" on Windows). Network requests (rules
update, ARES) can take seconds too.

Pattern used: a plain ``QObject`` "worker" moved to a ``QThread`` with
``moveToThread``. Results travel back through signals; Qt queues signal
delivery across threads automatically, so slots run in the GUI thread and may
touch widgets safely. (Subclassing ``QThread`` and overriding ``run`` also
works, but mixes "the thread" with "the work" and is discouraged by Qt docs.)
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ..core.ares import AresError, lookup
from ..core.loader import find_documents, load_documents
from ..core.rules import RulesError, RulesRepository


class LoadWorker(QObject):
    progress = Signal(int, int, str)  # done, total, file name
    finished = Signal(object)  # LoadResult

    def __init__(self, folder: Path, my_ico: str | None = None) -> None:
        super().__init__()
        self._folder = folder
        self._my_ico = my_ico

    @Slot()
    def run(self) -> None:
        paths = find_documents(self._folder)
        result = load_documents(
            paths,
            progress=lambda done, total, path: self.progress.emit(done, total, path.name),
            my_ico=self._my_ico,
        )
        self.finished.emit(result)


class RulesUpdateWorker(QObject):
    finished = Signal(object)  # UpdateResult
    failed = Signal(str)

    def __init__(self, repository: RulesRepository) -> None:
        super().__init__()
        self._repository = repository

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(self._repository.update_from_remote())
        except (OSError, RulesError, ValueError) as exc:
            self.failed.emit(str(exc))


class AresWorker(QObject):
    finished = Signal(object)  # AresInfo
    failed = Signal(str)

    def __init__(self, ico: str) -> None:
        super().__init__()
        self._ico = ico

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(lookup(self._ico))
        except AresError as exc:
            self.failed.emit(str(exc))


def start_in_thread(worker: QObject, parent: QObject) -> QThread:
    """Run ``worker.run`` in a new thread that cleans itself up.

    The caller must keep a reference to the returned thread (and the worker)
    until it finishes - otherwise Python's garbage collector may destroy the
    QThread while it is still running, which crashes the process.
    """
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    for name in ("finished", "failed"):
        signal = getattr(worker, name, None)
        if signal is not None:
            signal.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread
