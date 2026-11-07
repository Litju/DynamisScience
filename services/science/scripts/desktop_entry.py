"""PyInstaller entry point for the native GUI and its hidden worker mode."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _database_smoke(data_root: str, response_path: str) -> int:
    os.environ["DYNAMISSCIENCE_DATA_ROOT"] = data_root
    from dynamis_science.desktop.services import DynamisAppService

    try:
        service = DynamisAppService()
        verification = service.verify_research_database()
        backup = service.backup_research_database()
        restore = service.rehearse_research_restore(backup["path"])
        result = {"verification": verification, "backup": backup, "restore": restore}
    except Exception as error:
        result = {"type": type(error).__name__, "message": str(error)}
        Path(response_path).write_text(json.dumps(result), encoding="utf-8")
        return 1
    Path(response_path).write_text(
        json.dumps(result, sort_keys=True, default=str), encoding="utf-8"
    )
    return 0


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "--worker":
        from dynamis_science.desktop.worker import run_files

        return run_files(sys.argv[2], sys.argv[3])
    if len(sys.argv) == 4 and sys.argv[1] == "--database-smoke":
        return _database_smoke(sys.argv[2], sys.argv[3])
    from dynamis_science.desktop.__main__ import main as desktop_main

    return desktop_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
