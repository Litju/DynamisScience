"""Admit the RES-587 real datasets into the immutable store.

Run from the repository root:

    $env:DYNAMISSCIENCE_DATA_ROOT = Join-Path $env:LOCALAPPDATA 'DynamisScience'
    .\\services\\science\\.venv\\Scripts\\python.exe -m dynamis_science.ingest_real --source mendeley
    .\\services\\science\\.venv\\Scripts\\python.exe -m dynamis_science.ingest_real --source movesmart

The command is idempotent: identical content resolves to the existing snapshot;
different content under the same id is refused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .data_root import data_root, ensure_layout, paths
from . import real_mendeley, real_movesmart, realstore
from .real_sources import MENDELEY_SOURCE, ZENODO_SOURCE


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify(path: Path, expected: str, algorithm: str = "sha256") -> None:
    if algorithm == "md5":
        digest = hashlib.md5()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        actual = digest.hexdigest()
    else:
        actual = _sha256(path)
    if actual.lower() != expected.lower():
        raise SystemExit(f"Checksum mismatch for {path}: {actual} != {expected}")


def ingest_mendeley() -> dict:
    root = ensure_layout()
    source_path = root / "sources" / "mendeley-6p99569x66" / "DATA.xlsx"
    if not source_path.exists():
        raise SystemExit(f"Missing source file: {source_path}")
    expected = MENDELEY_SOURCE["files"][0]["sha256"]
    _verify(source_path, expected)
    tables = real_mendeley.build_tables(source_path)
    assessment = real_mendeley.assess(tables, source_path)
    if assessment["status"] == "REJECTED":
        raise SystemExit(f"Mendeley source rejected: {assessment['errors']}")
    snapshot = real_mendeley.write_snapshot(tables, assessment)
    return {"source": MENDELEY_SOURCE["id"], "snapshot": snapshot["id"], "status": assessment["status"], "counts": assessment["counts"]}


def ingest_movesmart(progress: bool = True) -> dict:
    root = ensure_layout()
    archive = root / "sources" / "zenodo-17376717" / "Dataset.zip"
    extracted = root / "extracted" / "zenodo-17376717" / "Dataset"
    if not archive.exists():
        raise SystemExit(f"Missing source archive: {archive}")
    if not extracted.exists():
        raise SystemExit(f"Missing extracted archive: {extracted}. Run the filtered extraction step first.")
    _verify(archive, ZENODO_SOURCE["files"][0]["md5"], "md5")
    callback = None
    if progress:
        def callback(position: int, total: int) -> None:
            if position == 1 or position % 25 == 0 or position == total:
                print(f"  parsing matched trials {position}/{total}", flush=True)
    tables, index = real_movesmart.build_tables(extracted, progress=callback)
    assessment = real_movesmart.assess(tables, index, archive)
    if assessment["status"] == "REJECTED":
        raise SystemExit(f"MoveSmart source rejected: {assessment['errors']}")
    snapshot = real_movesmart.write_snapshot(tables, assessment)
    return {"source": ZENODO_SOURCE["id"], "snapshot": snapshot["id"], "status": assessment["status"], "counts": assessment["counts"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Admit RES-587 real datasets")
    parser.add_argument("--source", choices=["mendeley", "movesmart", "all"], default="all")
    args = parser.parse_args(argv)
    ensure_layout()
    print(f"data root: {data_root()}")
    results = []
    if args.source in {"mendeley", "all"}:
        print("Admitting Mendeley Sprint Priming ...", flush=True)
        results.append(ingest_mendeley())
    if args.source in {"movesmart", "all"}:
        print("Admitting MoveSmart wearable + force plate ...", flush=True)
        results.append(ingest_movesmart())
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
