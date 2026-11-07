"""Create, verify, and stage a private SQLite Online Backup API recovery."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

from dynamis_science.data_root import DataRootConfigurationError, ROOT, data_root


class RecoveryError(RuntimeError):
    """Raised when a private research-store backup cannot be trusted."""


def _within(path: Path, parent: Path) -> bool:
    return path == parent or path.is_relative_to(parent)


def _private_path(value: str | Path, root: Path, label: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise RecoveryError(f"{label} must be an absolute path")
    if path.is_symlink():
        raise RecoveryError(f"{label} cannot be a symbolic link")
    path = path.resolve()
    if not _within(path, root) or path.is_relative_to(ROOT):
        raise RecoveryError(f"{label} must remain inside the private data root")
    return path


def _readonly(database: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True, timeout=30)


def inspect_database(database: Path) -> dict[str, Any]:
    if not database.is_file():
        raise RecoveryError(f"Research database not found: {database}")
    connection = _readonly(database)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
        violations = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        required = {"projects", "entities", "runs", "evidence", "audit"}
        if missing := required.difference(tables):
            raise RecoveryError(f"Research schema is missing tables: {', '.join(sorted(missing))}")
        counts = {}
        for name in tables:
            table = '"' + name.replace('"', '""') + '"'
            counts[name] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        record_counts = {
            "projects": counts["projects"],
            "studies": connection.execute(
                "SELECT COUNT(*) FROM entities WHERE kind='STUDY'"
            ).fetchone()[0],
            "monitoring_programs": connection.execute(
                "SELECT COUNT(*) FROM entities WHERE kind='MONITORING'"
            ).fetchone()[0],
            "runs": counts["runs"],
            "evidence": counts["evidence"],
            "audit_records": counts["audit"],
        }
        digest = hashlib.sha256()
        for line in connection.iterdump():
            digest.update(line.encode("utf-8"))
            digest.update(b"\n")
        summary = {
            "database": str(database),
            "bytes": database.stat().st_size,
            "integrity_check": integrity,
            "foreign_key_violations": violations,
            "foreign_keys": connection.execute("PRAGMA foreign_keys").fetchone()[0],
            "journal_mode": connection.execute("PRAGMA journal_mode").fetchone()[0],
            "schema_version": connection.execute("PRAGMA user_version").fetchone()[0],
            "tables": tables,
            "table_count": len(tables),
            "row_counts": counts,
            "record_counts": record_counts,
            "logical_sha256": digest.hexdigest(),
        }
    finally:
        connection.close()
    if integrity != ["ok"] or violations or summary["foreign_keys"] != 1:
        raise RecoveryError(f"SQLite integrity or foreign-key check failed: {summary}")
    if summary["schema_version"] < 1:
        raise RecoveryError("Research database has no recognized schema version")
    return summary


def _same_database_state(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return all(
        left[key] == right[key]
        for key in ("schema_version", "tables", "row_counts", "record_counts", "logical_sha256")
    )


def backup_database(destination: Path) -> dict[str, Any]:
    root = data_root()
    source = root / "research" / "research.db"
    destination = _private_path(destination, root, "Backup path")
    if destination == source.resolve():
        raise RecoveryError("Backup path must be separate from the operational database")
    if destination.exists() or destination.is_symlink():
        raise RecoveryError(f"Refusing to overwrite existing backup: {destination}")

    before = inspect_database(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = _readonly(source)
    target_connection = sqlite3.connect(str(destination), timeout=30)
    try:
        target_connection.execute("PRAGMA synchronous=FULL")
        source_connection.backup(target_connection)
        checkpoint = target_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if checkpoint is None or checkpoint[0] != 0:
            raise RecoveryError("Backup WAL could not be checkpointed")
        journal_mode = target_connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
        if str(journal_mode).lower() != "delete":
            raise RecoveryError("Backup database could not be closed out as a standalone file")
    finally:
        target_connection.close()
        source_connection.close()

    after = inspect_database(source)
    backup = inspect_database(destination)
    if not _same_database_state(before, after):
        raise RecoveryError("Operational database records changed while taking the backup")
    if not _same_database_state(before, backup):
        raise RecoveryError("Online backup does not match the operational database")
    return {"source": after, "backup": backup}


def _copy_recovery_assets(source_root: Path, destination_root: Path) -> None:
    for name in ("snapshots", "manifests", "qualification"):
        source = source_root / name
        if not source.exists():
            continue
        if source.is_symlink():
            raise RecoveryError(f"Refusing to copy a symlinked private recovery directory: {source}")
        if any(path.is_symlink() for path in source.rglob("*")):
            raise RecoveryError(f"Refusing to follow a symlink in private recovery data: {source}")
        shutil.copytree(source, destination_root / name)


def _reopen_through_application(root: Path, expected: dict[str, Any]) -> dict[str, Any]:
    previous_root = os.environ.get("DYNAMISSCIENCE_DATA_ROOT")
    os.environ["DYNAMISSCIENCE_DATA_ROOT"] = str(root)
    try:
        from dynamis_science import researchstore

        projects = researchstore.list_projects(include_archived=True)
        studies = researchstore.list_entities(kind="STUDY")
        programs = researchstore.list_entities(kind="MONITORING")
        runs = researchstore.list_runs()
        evidence = researchstore.list_evidence()
        counts = {
            "projects": len(projects),
            "studies": len(studies),
            "monitoring_programs": len(programs),
            "runs": len(runs),
            "evidence": len(evidence),
        }
        for key, value in counts.items():
            if value != expected["record_counts"][key]:
                raise RecoveryError(f"Application reopened {key}={value}; expected {expected['record_counts'][key]}")
        lineage_counts = [len(researchstore.lineage(item["id"])["nodes"]) for item in evidence]
        return {"record_counts": counts, "evidence_lineage_node_counts": lineage_counts}
    finally:
        if previous_root is None:
            os.environ.pop("DYNAMISSCIENCE_DATA_ROOT", None)
        else:
            os.environ["DYNAMISSCIENCE_DATA_ROOT"] = previous_root


def restore_database(backup: Path, destination_root: Path) -> dict[str, Any]:
    root = data_root()
    backup = _private_path(backup, root, "Backup path")
    destination_root = data_root(destination_root)
    destination_root = _private_path(destination_root, root / "tmp", "Restore root")
    if not backup.is_file():
        raise RecoveryError(f"Backup not found: {backup}")
    if backup == (root / "research" / "research.db").resolve():
        raise RecoveryError("Restore source must be a separate backup file")
    if destination_root == root or destination_root.exists() or destination_root.is_symlink():
        raise RecoveryError(f"Refusing to replace existing restore root: {destination_root}")

    expected = inspect_database(backup)
    destination_root.mkdir(parents=True, exist_ok=False)
    _copy_recovery_assets(root, destination_root)
    destination = destination_root / "research" / "research.db"
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = _readonly(backup)
    target_connection = sqlite3.connect(str(destination), timeout=30)
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()

    restored = inspect_database(destination)
    if not _same_database_state(expected, restored):
        raise RecoveryError("Restored database does not match the backup")
    application = _reopen_through_application(destination_root, expected)
    reopened = inspect_database(destination)
    if not _same_database_state(expected, reopened):
        raise RecoveryError("Application reopening changed restored database records")
    return {
        "backup": expected,
        "restored": reopened,
        "application_reopen": application,
        "restore_root": str(destination_root),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify private SQLite Online Backup API recovery")
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup = subparsers.add_parser("backup", help="create a private database backup")
    backup.add_argument("--destination", required=True, type=Path)
    verify = subparsers.add_parser("verify", help="check a private SQLite database read-only")
    verify.add_argument("--database", required=True, type=Path)
    restore = subparsers.add_parser("restore", help="restore to a new private tmp root and reopen it")
    restore.add_argument("--backup", required=True, type=Path)
    restore.add_argument("--destination-root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        root = data_root()
        if args.command == "backup":
            result = backup_database(args.destination)
        elif args.command == "verify":
            database = _private_path(args.database, root, "Database path")
            result = inspect_database(database)
        else:
            result = restore_database(args.backup, args.destination_root)
        print(json.dumps(result, indent=2))
        return 0
    except (DataRootConfigurationError, RecoveryError, OSError, sqlite3.Error, shutil.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
