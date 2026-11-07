"""Read-only integrity and foreign-key check for the local research database."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from dynamis_science.data_root import DataRootConfigurationError, data_root


def main() -> int:
    try:
        database = data_root() / "research" / "research.db"
    except DataRootConfigurationError as exc:
        raise SystemExit(str(exc)) from exc
    if not database.is_file():
        raise SystemExit(f"Research database not found: {database}")

    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        result = {
            "database": str(database),
            "bytes": database.stat().st_size,
            "integrity_check": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "foreign_key_violations": len(
                connection.execute("PRAGMA foreign_key_check").fetchall()
            ),
            "foreign_keys": connection.execute("PRAGMA foreign_keys").fetchone()[0],
            "journal_mode": connection.execute("PRAGMA journal_mode").fetchone()[0],
            "schema_version": connection.execute("PRAGMA user_version").fetchone()[0],
            "table_count": len(tables),
            "row_counts": {
                name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                for name in tables
            },
        }
        print(json.dumps(result, indent=2))
        return int(
            result["integrity_check"] != "ok"
            or result["foreign_key_violations"] != 0
            or result["foreign_keys"] != 1
        )
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
