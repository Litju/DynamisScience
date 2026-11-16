"""Run scoped tests with a timeout, bounded scratch and automatic guarded cleanup.

Usage: python scripts/scoped_tests.py tests/test_method_catalogue.py
Only the new temporary directory is removed, including on failure or interruption.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


def scratch_bytes(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except FileNotFoundError:
            pass  # SQLite and Qt may remove transient files while sampled.
    return total


def main() -> int:
    parent = Path(tempfile.gettempdir()).resolve()
    service = Path(__file__).resolve().parents[1]
    protected = Path("D:/datasets/DynamisScience").resolve()
    if parent == protected or parent.is_relative_to(protected) or parent.is_relative_to(service.parents[1]):
        raise RuntimeError("Scratch parent must be outside the checkout and protected dataset")
    scratch = Path(tempfile.mkdtemp(prefix="res716-tests-", dir=parent)).resolve()
    if scratch.parent != parent or not scratch.name.startswith("res716-tests-"):
        raise RuntimeError("Unsafe scratch path")
    process = None
    peak = 0
    result = 1
    try:
        env = {**os.environ, **{key: str(scratch) for key in ("TEMP", "TMP", "TMPDIR")},
               "DYNAMISSCIENCE_DATA_ROOT": str(scratch / "data"), "QT_QPA_PLATFORM": "offscreen",
               "PYTHONDONTWRITEBYTECODE": "1", "MPLCONFIGDIR": str(scratch / "mpl")}
        env.pop("DYNAMISSCIENCE_TEST_SOURCE_ROOT", None)
        command = [sys.executable, "-m", "pytest", *sys.argv[1:], "--basetemp", str(scratch / "pytest"),
                   "-o", f"cache_dir={scratch / 'cache'}"]
        process = subprocess.Popen(command, cwd=service, env=env)
        started = time.monotonic()
        while process.poll() is None:
            peak = max(peak, scratch_bytes(scratch))
            if peak > 512 * 1024**2 or time.monotonic() - started > 300:
                raise RuntimeError("Scoped run exceeded 512 MiB scratch or 300 seconds")
            time.sleep(0.25)
        result = process.wait()
    finally:
        if process is not None and process.poll() is None:
            # Kill the worker tree before deleting only our verified scratch directory.
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
            process.wait(timeout=10)
        shutil.rmtree(scratch)
        print(json.dumps({"exit_code": result, "scratch_peak_bytes_sampled": peak,
                          "scratch_removed": not scratch.exists(), "limits": "512 MiB / 300 seconds"}))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
