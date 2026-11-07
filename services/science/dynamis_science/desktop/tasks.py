"""Qt thread-pool adapter for direct Python service calls."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Signals(QObject):
    result = Signal(object)
    failed = Signal(object)
    finished = Signal()


class _Task(QRunnable):
    def __init__(self, operation: Callable[[], Any]) -> None:
        super().__init__()
        self.operation = operation
        self.signals = _Signals()

    def run(self) -> None:
        try:
            self.signals.result.emit(self.operation())
        except Exception as error:
            self.signals.failed.emit(error)
        finally:
            self.signals.finished.emit()


class TaskRunner(QObject):
    """Run blocking service work off the GUI thread and deliver results via Qt."""

    _result = Signal(object, object)
    _failed = Signal(object, object)
    _finished = Signal(object)
    idle = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.active: set[_Task] = set()
        self.callbacks: dict[_Task, tuple[Callable[[Any], None], Callable[[Exception], None]]] = {}
        self._result.connect(self._deliver_result)
        self._failed.connect(self._deliver_error)
        self._finished.connect(self._forget)

    def _deliver_result(self, task: _Task, value: Any) -> None:
        callback, on_error = self.callbacks[task]
        try:
            callback(value)
        except Exception as error:
            on_error(error)

    def _deliver_error(self, task: _Task, error: Exception) -> None:
        _, callback = self.callbacks[task]
        callback(error)

    def _forget(self, task: _Task) -> None:
        self.callbacks.pop(task, None)
        self.active.discard(task)
        if not self.active:
            self.idle.emit()

    def submit(
        self,
        operation: Callable[[], Any],
        on_result: Callable[[Any], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        task = _Task(operation)
        self.active.add(task)
        self.callbacks[task] = (on_result, on_error)
        task.signals.result.connect(lambda value: self._result.emit(task, value))
        task.signals.failed.connect(lambda error: self._failed.emit(task, error))
        task.signals.finished.connect(lambda: self._finished.emit(task))
        self.pool.start(task)
