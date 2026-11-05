"""Configurable storage root for admitted third-party research data.

The repository never stores downloaded datasets.  Scientific data lives under
``DYNAMISSCIENCE_DATA_ROOT`` (default: ``<repo>/data/real``) with a stable,
purpose-specific layout.  All paths are derived with :mod:`pathlib` so the same
code runs on Windows, Linux and macOS.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ROOT = ROOT / "data" / "real"

LAYOUT = (
    "sources",
    "extracted",
    "quarantine",
    "admitted",
    "snapshots",
    "qualification",
    "manifests",
    "artifacts",
    "reports",
    "research",
    "tmp",
)


def data_root() -> Path:
    configured = os.environ.get("DYNAMISSCIENCE_DATA_ROOT", "").strip()
    return Path(configured).expanduser().resolve() if configured else DEFAULT_ROOT


def ensure_layout(root: Path | None = None) -> Path:
    base = root or data_root()
    base.mkdir(parents=True, exist_ok=True)
    for name in LAYOUT:
        (base / name).mkdir(parents=True, exist_ok=True)
    return base


def paths(root: Path | None = None) -> dict[str, Path]:
    base = ensure_layout(root)
    return {name: base / name for name in LAYOUT} | {"root": base}


def source_dir(source_id: str) -> Path:
    path = paths()["sources"] / source_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshot_dir(snapshot_id: str) -> Path:
    path = paths()["snapshots"] / snapshot_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def manifest_dir() -> Path:
    return paths()["manifests"]


def qualification_dir() -> Path:
    return paths()["qualification"]
