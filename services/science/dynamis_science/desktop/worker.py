"""Isolated worker process for CPU-heavy, qualified scientific analyses."""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    request = json.load(sys.stdin)
    os.environ["DYNAMISSCIENCE_DATA_ROOT"] = request["data_root"]
    try:
        from .services import DynamisAppService

        result = DynamisAppService().execute_analysis_run(
            request["study_id"], request["payload"]
        )
    except Exception as error:
        json.dump({"type": type(error).__name__, "message": str(error)}, sys.stderr)
        return 1
    json.dump(result, sys.stdout, sort_keys=True, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
