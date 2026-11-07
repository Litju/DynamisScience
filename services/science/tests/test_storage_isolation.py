from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


SCIENCE_ROOT = Path(__file__).resolve().parents[1]
PROBE = Path(__file__).with_name("test_storage_isolation_probe.py")


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_inherited_simulated_operational_root_is_never_touched(tmp_path):
    simulated_root = tmp_path / "simulated-operational-root"
    simulated_root.mkdir()
    sentinel = simulated_root / "sentinel.txt"
    sentinel.write_text("preserve this operational sentinel", encoding="utf-8")
    database = simulated_root / "research" / "research.db"
    database.parent.mkdir()
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
    connection.execute("INSERT INTO sentinel VALUES ('preserve this database row')")
    connection.commit()
    before = _file_hashes(simulated_root)

    env = os.environ.copy()
    env["DYNAMISSCIENCE_DATA_ROOT"] = str(simulated_root)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(PROBE)],
        cwd=SCIENCE_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    after = _file_hashes(simulated_root)
    connection.close()
    assert result.returncode == 0, f"nested pytest failed:\n{result.stdout}\n{result.stderr}"
    assert after == before
