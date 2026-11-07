"""Isolated worker process for CPU-heavy, qualified scientific analyses."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _execute(request: dict) -> dict:
    os.environ["DYNAMISSCIENCE_DATA_ROOT"] = request["data_root"]
    from .services import DynamisAppService

    return DynamisAppService().execute_analysis_run(
        request["study_id"], request["payload"]
    )


def main() -> int:
    request = json.load(sys.stdin)
    try:
        result = _execute(request)
    except Exception as error:
        json.dump({"type": type(error).__name__, "message": str(error)}, sys.stderr)
        return 1
    json.dump(result, sys.stdout, sort_keys=True, default=str)
    return 0


def run_files(request_path: str | Path, response_path: str | Path) -> int:
    """File-based IPC for the frozen windowed executable's hidden worker mode."""
    try:
        request = json.loads(Path(request_path).read_text(encoding="utf-8"))
        result = _execute(request)
    except Exception as error:
        result = {"type": type(error).__name__, "message": str(error)}
        Path(response_path).write_text(json.dumps(result), encoding="utf-8")
        return 1
    Path(response_path).write_text(
        json.dumps(result, sort_keys=True, default=str), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
