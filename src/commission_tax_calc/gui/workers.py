"""Background work: parsing PDFs and downloading rules off the GUI thread.

Why threads: pdfplumber needs ~0.1-0.3 s per statement and a year has ~24 of
them. Doing that in the GUI thread would freeze the window (no repaint, "Not
responding" on Windows). The network request for rules can take seconds too.

Pattern used: a plain ``QObject`` "worker" moved to a ``QThread`` with
``moveToThread``. Results travel back through signals; Qt queues signal
delivery across threads automatically, so slots run in the GUI thread and may
touch widgets safely. (Subclassing ``QThread`` and overriding ``run`` also
works, but mixes "the thread" with "the work" and is discouraged by Qt docs.)
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ..core.loader import find_pdfs, load_statements
from ..core.rules import RulesError, RulesRepository


class LoadWorker(QObject):
    progress = Signal(int, int, str)  # done, total, file name
    finished = Signal(object)  # LoadResult

    def __init__(self, folder: Path) -> None:
        super().__init__()
        self._folder = folder

    @Slot()
    def run(self) -> None:
        paths = find_pdfs(self._folder)
        result = load_statements(
            paths, progress=lambda done, total, path: self.progress.emit(done, total, path.name)
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
