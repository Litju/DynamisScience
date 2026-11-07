"""Measure native Performance OS page latency using only the synthetic fixture."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from dynamis_science.desktop.main_window import MainWindow
from dynamis_science.desktop.services import DynamisAppService


def _working_set() -> tuple[int, int]:
    from ctypes import wintypes

    class MemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(MemoryCounters),
        wintypes.DWORD,
    )
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)


def _wait(app: QApplication, predicate, errors: list[str], timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if errors:
            raise RuntimeError(errors.pop(0))
        if predicate():
            return
        time.sleep(0.005)
    raise TimeoutError("Timed out waiting for a Performance OS page")


def measure(evidence_dir: Path | None = None) -> dict[str, object]:
    errors: list[str] = []
    QMessageBox.warning = lambda *_args: errors.append(str(_args[-1]))
    with tempfile.TemporaryDirectory(prefix="dynamis-performance-bench-") as root:
        os.environ["DYNAMISSCIENCE_DATA_ROOT"] = root
        app = QApplication(sys.argv[:1])
        window = MainWindow(DynamisAppService())
        window.show()
        _wait(app, lambda: window.navigator.topLevelItemCount() == 4, errors)
        performance_root = window.navigator.topLevelItem(3)
        last_tick = [time.perf_counter()]
        max_gap = [0.0]

        def tick() -> None:
            now = time.perf_counter()
            max_gap[0] = max(max_gap[0], now - last_tick[0])
            last_tick[0] = now

        monitor = QTimer()
        monitor.setInterval(1)
        monitor.setTimerType(Qt.TimerType.PreciseTimer)
        monitor.timeout.connect(tick)
        monitor.start()
        latency = []
        screenshots = []
        athlete_drawer_latency = None
        for index, page in enumerate(window.performance.page_keys):
            started = time.perf_counter()
            max_gap[0] = 0.0
            last_tick[0] = started
            window._navigation_activated(performance_root.child(index), 0)
            _wait(
                app,
                lambda page=page: page in window.performance.loaded_pages and not window.runner.active,
                errors,
            )
            if page == "match":
                _wait(
                    app,
                    lambda: bool(window.performance.pose_plot.plotItem.listDataItems()),
                    errors,
                )
            measurement = {
                "page": page,
                "loaded_ms": round((time.perf_counter() - started) * 1000, 3),
                "maximum_gui_timer_gap_ms": round(max_gap[0] * 1000, 3),
            }
            latency.append(measurement)
            if evidence_dir and page in {"today", "match"}:
                app.processEvents()
                filename = f"g3-performance-{page}.png"
                evidence_dir.mkdir(parents=True, exist_ok=True)
                if not window.grab().save(str(evidence_dir / filename)):
                    raise RuntimeError(f"Could not capture native UI evidence: {filename}")
                screenshots.append(filename)
                if page == "today":
                    drawer_started = time.perf_counter()
                    window.performance._open_selected_athlete()
                    _wait(
                        app,
                        lambda: window.performance.context_panel.views.currentWidget()
                        is window.performance.context_panel.athlete_view
                        and not window.runner.active,
                        errors,
                    )
                    athlete_drawer_latency = round((time.perf_counter() - drawer_started) * 1000, 3)
                    filename = "g3-performance-athlete.png"
                    if not window.grab().save(str(evidence_dir / filename)):
                        raise RuntimeError(f"Could not capture native UI evidence: {filename}")
                    screenshots.append(filename)
                    window._show_daily_context()
        monitor.stop()
        working_set, peak_working_set = _working_set()
        window.close()
        app.quit()
        return {
            "environment": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "data": "DS-SYNTH-001 only; operational writes isolated in a temporary data root",
            },
            "measurements": {
                "page_load_latency": latency,
                "working_set_mb": round(working_set / 1024**2, 2),
                "peak_working_set_mb": round(peak_working_set / 1024**2, 2),
                "athlete_360_drawer_load_ms": athlete_drawer_latency,
                "screenshots": screenshots,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()
    if not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = (
            "windows" if args.evidence_dir and os.name == "nt" else "offscreen"
        )
    result = measure(args.evidence_dir)
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
