from __future__ import annotations

from dynamis_science import researchstore
from scripts.sqlite_recovery import backup_database, inspect_database, restore_database


def test_wal_online_backup_restores_and_reopens_separately(monkeypatch, tmp_path):
    root = tmp_path / "private-store"
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(root))
    researchstore.create_project("Recovery fixture", "Synthetic backup test")
    source = inspect_database(root / "research" / "research.db")

    backup_path = root / "backups" / "research-test.sqlite3"
    backup = backup_database(backup_path)
    restored = restore_database(backup_path, root / "tmp" / "restore-test")
    restored_path = root / "tmp" / "restore-test" / "research" / "research.db"
    verified = inspect_database(restored_path)

    assert backup["source"]["logical_sha256"] == source["logical_sha256"]
    assert restored["backup"]["logical_sha256"] == verified["logical_sha256"]
    assert restored["application_reopen"]["record_counts"]["projects"] == 1
    assert verified["record_counts"]["projects"] == 1
    assert verified["journal_mode"].lower() == "wal"
