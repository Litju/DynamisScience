"""Measure the native desktop workload against disposable private-data copies."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from PySide6.QtCore import Qt

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from dynamis_science.data_root import data_root
from dynamis_science.desktop.main_window import MainWindow
from dynamis_science.desktop.services import DynamisAppService

_TASK_ERRORS: list[str] = []


def _copy_store(source: Path, target: Path) -> None:
    snapshots = sorted((source / "snapshots").glob("DS-REAL-*"))
    if len(snapshots) < 2:
        raise RuntimeError("The source root must contain the admitted Mendeley and MoveSmart snapshots")
    (target / "manifests").mkdir(parents=True)
    (target / "snapshots").mkdir()
    (target / "research").mkdir()
    shutil.copy2(source / "manifests" / "admissions.json", target / "manifests")
    for snapshot in snapshots:
        copied = target / "snapshots" / snapshot.name
        shutil.copytree(snapshot, copied)
        manifest = json.loads((copied / "snapshot.json").read_text(encoding="utf-8"))
        for filename, expected in manifest.get("checksums", {}).items():
            with (copied / filename).open("rb") as handle:
                actual = hashlib.file_digest(handle, "sha256").hexdigest()
            if actual != expected:
                raise RuntimeError(f"Snapshot copy failed checksum verification: {copied.name}/{filename}")
    source_db = sqlite3.connect(
        f"file:{(source / 'research' / 'research.db').as_posix()}?mode=ro", uri=True
    )
    target_db = sqlite3.connect(target / "research" / "research.db")
    try:
        source_db.backup(target_db)
    finally:
        target_db.close()
        source_db.close()


def _working_set() -> tuple[int, int]:
    if os.name != "nt":
        raise RuntimeError("Working-set benchmarks require Windows")

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
    handle = kernel32.GetCurrentProcess()
    ok = psapi.GetProcessMemoryInfo(
        handle, ctypes.byref(counters), counters.cb
    )
    if not ok:
        raise ctypes.WinError()
    return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)


def _wait_for(predicate, timeout_seconds: int = 60) -> None:
    if predicate():
        return
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(20)
    def check() -> None:
        if _TASK_ERRORS:
            loop.quit()
        elif predicate():
            loop.quit()

    poll.timeout.connect(check)
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    poll.start()
    timeout.start(timeout_seconds * 1000)
    loop.exec()
    poll.stop()
    if _TASK_ERRORS:
        raise RuntimeError(_TASK_ERRORS.pop(0))
    if not predicate():
        raise TimeoutError("Timed out waiting for the desktop benchmark operation")


def _startup_sample(script: Path, root: Path, environment: dict[str, str]) -> float:
    started = time.perf_counter()
    print("benchmark: startup child launch", file=sys.stderr, flush=True)
    startup_code = """
import time
from PySide6.QtWidgets import QApplication
from dynamis_science.desktop.main_window import MainWindow
from dynamis_science.desktop.services import DynamisAppService
app = QApplication([])
window = MainWindow(DynamisAppService())
window.catalogue_loaded.connect(lambda: print(f'BENCHMARK_READY {time.perf_counter():.9f}', flush=True))
window.runner.idle.connect(lambda: app.quit() if not window.runner.active else None)
window.show()
raise SystemExit(app.exec())
"""
    process = subprocess.Popen(
        [sys.executable, "-c", startup_code],
        cwd=script.parents[1],
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        output, errors = process.communicate(timeout=120)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise TimeoutError("The desktop did not populate its catalogue within 120 seconds")
    ready = next(
        (float(line.split()[1]) for line in output.splitlines() if line.startswith("BENCHMARK_READY ")),
        None,
    )
    if process.returncode or ready is None:
        raise RuntimeError(f"Startup child failed: {errors.strip() or output.strip()}")
    print("benchmark: startup child ready", file=sys.stderr, flush=True)
    return (ready - started) * 1000


def _find_study_item(window: MainWindow, study_id: str):
    parent = window.navigator.topLevelItem(1)
    for index in range(parent.childCount()):
        item = parent.child(index)
        if item.data(0, Qt.ItemDataRole.UserRole).get("id") == study_id:
            return item
    raise RuntimeError(f"Study {study_id} is missing from the native catalogue")


def _open_study(window: MainWindow, study_id: str) -> None:
    window._navigation_activated(_find_study_item(window, study_id), 0)
    _wait_for(lambda: window.current_study_id == study_id)
    _wait_for(lambda: not window.runner.active)


def _measure(root: Path) -> dict[str, object]:
    os.environ["DYNAMISSCIENCE_DATA_ROOT"] = str(root)
    QMessageBox.warning = lambda *_args: _TASK_ERRORS.append(str(_args[-1]))
    service = DynamisAppService()
    app = QApplication(sys.argv[:1])
    window = MainWindow(service)
    window.show()
    _wait_for(lambda: window.catalogue_loaded is not None and window.status_text.text() == "Ready")
    _wait_for(lambda: not window.runner.active)
    print("benchmark: catalog ready", file=sys.stderr, flush=True)
    studies = service.list_all_studies()
    mendeley = next(
        study
        for study in studies
        if study.get("id", "").startswith("STUDY-U-")
        and study.get("dataset_snapshot_id") == "DS-REAL-MENDELEY-2C44490E08AD"
    )
    movesmart = next(study for study in studies if study.get("id") == "STUDY-REAL-002")
    _open_study(window, mendeley["id"])
    print("benchmark: Mendeley opened", file=sys.stderr, flush=True)
    loop = QEventLoop()
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    idle_rss, _ = _working_set()
    print("benchmark: idle memory sampled", file=sys.stderr, flush=True)

    _open_study(window, movesmart["id"])
    print("benchmark: MoveSmart opened", file=sys.stderr, flush=True)
    force_index = window.research.table_picker.findText("force_signals")
    if force_index < 0:
        raise RuntimeError("MoveSmart force_signals table is not in the admitted snapshot")
    subjects_index = window.research.table_picker.findText("subjects")
    if subjects_index >= 0:
        window.research.table_picker.setCurrentIndex(subjects_index)
        _wait_for(lambda: not window.research.table_model.loading)
    rss_before_page, _ = _working_set()
    page_started = time.perf_counter()
    window.research.table_picker.setCurrentIndex(force_index)
    _wait_for(lambda: window.research.table_model.rowCount() == 500)
    page_ms = (time.perf_counter() - page_started) * 1000
    print("benchmark: Parquet page loaded", file=sys.stderr, flush=True)
    page_rows = window.research.table_model.rowCount()
    rss_after_page, _ = _working_set()

    walking = next(
        (index for index in range(window.research.trial_picker.count())
         if "Walking" in window.research.trial_picker.itemText(index)),
        None,
    )
    if walking is None:
        raise RuntimeError("MoveSmart contains no Walking trials")
    window.research.trial_picker.setCurrentIndex(walking)
    waveform_started = time.perf_counter()
    window.research._load_signal()
    _wait_for(lambda: window.research.table_status.text().startswith("Signal "))
    app.processEvents()
    waveform_ms = (time.perf_counter() - waveform_started) * 1000
    print("benchmark: waveform rendered", file=sys.stderr, flush=True)

    _open_study(window, mendeley["id"])
    print("benchmark: Mendeley reopened", file=sys.stderr, flush=True)
    detail = service.get_study_detail(mendeley["id"])
    plan = detail["plan"]
    window.research.method_picker.setCurrentIndex(
        window.research.method_picker.findData(plan["method_id"])
    )
    window.research.analysis_metric_picker.setCurrentIndex(
        window.research.analysis_metric_picker.findData(plan["outcome_metric_id"])
    )
    window.research.parameters.setPlainText(json.dumps(plan.get("parameters", {})))
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
    analysis_started = time.perf_counter()
    window.research._execute()
    _wait_for(lambda: window.research.latest_run is not None, timeout_seconds=120)
    print("benchmark: MixedLM completed", file=sys.stderr, flush=True)
    monitor.stop()
    wall_ms = (time.perf_counter() - analysis_started) * 1000
    run = window.research.latest_run
    window.research._promote()
    _wait_for(lambda: window.research.latest_evidence_id is not None)
    window.research._cite_latest()
    _wait_for(
        lambda: any(
            item.get("artifact_id") == window.research.latest_evidence_id
            for item in service.get_report(mendeley["id"]).get("citations", [])
        )
    )
    window.research._freeze_report()
    _wait_for(lambda: window.research.report_version is not None)
    report = root / "tmp" / "benchmark-report.html"
    service.export_report_html(mendeley["id"], report, window.research.report_version)
    print("benchmark: report exported", file=sys.stderr, flush=True)
    working_set, peak_working_set = _working_set()
    _wait_for(lambda: not window.runner.active)
    window.close()
    app.quit()
    return {
        "benchmarks": {
            "BENCH-02-IDLE-RAM": {"working_set_mb": round(idle_rss / 1024**2, 2), "delay_after_study_open_s": 5},
            "BENCH-03-PARQUET-PAGE": {
                "table": "force_signals",
                "rows": page_rows,
                "latency_ms": round(page_ms, 3),
                "working_set_delta_mb": round((rss_after_page - rss_before_page) / 1024**2, 2),
            },
            "BENCH-04-WAVEFORM-LOAD": {"latency_ms": round(waveform_ms, 3)},
            "BENCH-05-MIXEDLM-RUN": {
                "method_id": run["method_id"],
                "status": run["status"],
                "worker_duration_ms": run["duration_ms"],
                "wall_ms": round(wall_ms, 3),
                "max_gui_timer_gap_ms": round(max_gap[0] * 1000, 3),
            },
            "BENCH-06-PEAK-RSS": {
                "working_set_mb": round(working_set / 1024**2, 2),
                "peak_working_set_mb": round(peak_working_set / 1024**2, 2),
                "report_exported": report.is_file(),
            },
        }
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", help="verified private source root to copy read-only")
    parser.add_argument("--output", type=Path, help="optional JSON output file")
    args = parser.parse_args(argv)
    source_root = data_root(args.source_root)
    script = Path(__file__).resolve()
    with tempfile.TemporaryDirectory(prefix="dynamis-science-benchmark-") as temporary:
        isolated_root = Path(temporary) / "private"
        _copy_store(source_root, isolated_root)
        environment = os.environ.copy()
        environment["DYNAMISSCIENCE_DATA_ROOT"] = str(isolated_root)
        cold_starts = [
            _startup_sample(script, isolated_root, environment)
            for _ in range(5)
        ]
        print("benchmark: cold-start samples collected", file=sys.stderr, flush=True)
        result = {
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "windows_release": platform.release(),
            "windows_version": platform.version(),
            "qt_platform": os.environ.get("QT_QPA_PLATFORM", "platform default"),
            "input_data": "checksum-verified snapshots and SQLite backup in a disposable temporary root",
            "BENCH-01-COLD-START": {
                "samples": [round(value, 3) for value in cold_starts],
                "median_ms": round(statistics.median(cold_starts), 3),
                "p95_ms": round(statistics.quantiles(cold_starts, n=20, method="inclusive")[18], 3),
            },
            **_measure(isolated_root),
        }
    encoded = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8", newline="\n")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
