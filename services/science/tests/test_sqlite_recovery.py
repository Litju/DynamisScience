from __future__ import annotations

from pathlib import Path

import pytest

from dynamis_science import researchstore
from scripts import sqlite_recovery
from scripts.sqlite_recovery import backup_database, inspect_database, restore_database


def test_wal_online_backup_restores_and_reopens_separately(monkeypatch, tmp_path):
    root = tmp_path / "private-store"
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(root))
    researchstore.create_project("Recovery fixture", "Synthetic backup test")
    source = inspect_database(root / "research" / "research.db")

    backup_path = root / "backups" / "research-test.sqlite3"
    backup = backup_database(backup_path)
    assert backup["backup"]["journal_mode"].lower() == "delete"
    assert not Path(f"{backup_path}-wal").exists()
    assert not Path(f"{backup_path}-shm").exists()
    restored = restore_database(backup_path, root / "tmp" / "restore-test")
    restored_path = root / "tmp" / "restore-test" / "research" / "research.db"
    verified = inspect_database(restored_path)

    assert backup["source"]["logical_sha256"] == source["logical_sha256"]
    assert restored["backup"]["logical_sha256"] == verified["logical_sha256"]
    assert restored["application_reopen"]["record_counts"]["projects"] == 1
    assert verified["record_counts"]["projects"] == 1
    assert verified["journal_mode"].lower() == "wal"


def test_recovery_paths_use_installed_application_boundary(monkeypatch, tmp_path):
    install_dir = tmp_path / "installed-app"
    private_root = tmp_path / "private-data"
    install_dir.mkdir()
    private_root.mkdir()
    monkeypatch.setattr(sqlite_recovery, "ROOT", install_dir)
    backup = private_root / "backups" / "research.sqlite3"
    backup.parent.mkdir()

    assert sqlite_recovery._private_path(backup, private_root, "Backup path") == backup
    with pytest.raises(sqlite_recovery.RecoveryError, match="private data root"):
        sqlite_recovery._private_path(install_dir / "research.sqlite3", private_root, "Backup path")
