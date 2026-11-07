"""Resolve private scientific storage without import-time environment state."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
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
    "performance",
    "research",
    "tmp",
)


class DataRootConfigurationError(RuntimeError):
    """Raised when private scientific storage is missing or unsafe."""


def _within(path: Path, parent: Path) -> bool:
    return path == parent or path.is_relative_to(parent)


def _validate_root(root: Path) -> Path:
    if not root.is_absolute():
        raise DataRootConfigurationError("DYNAMISSCIENCE_DATA_ROOT must be an absolute path")
    base = root.expanduser().resolve()
    if _within(base, ROOT):
        raise DataRootConfigurationError("DYNAMISSCIENCE_DATA_ROOT must be outside the repository")
    if base.exists() and not base.is_dir():
        raise DataRootConfigurationError("DYNAMISSCIENCE_DATA_ROOT must be a directory")

    protected = os.environ.get("DYNAMISSCIENCE_TEST_PROTECTED_ROOTS", "")
    if protected:
        try:
            blocked_roots = [Path(item).expanduser().resolve() for item in json.loads(protected)]
        except (TypeError, ValueError) as exc:
            raise DataRootConfigurationError("Invalid test storage protection configuration") from exc
        if any(_within(base, item) or _within(item, base) for item in blocked_roots):
            raise DataRootConfigurationError("Tests cannot access an inherited operational data root")

    if os.environ.get("DYNAMISSCIENCE_TEST_SESSION") == "1":
        test_temp = Path(tempfile.gettempdir()).resolve()
        if not _within(base, test_temp):
            raise DataRootConfigurationError("Tests may use only temporary data roots")
    return base


def data_root(root: str | os.PathLike[str] | None = None) -> Path:
    """Return the explicitly configured private root, or validate a supplied root."""
    configured = str(root) if root is not None else os.environ.get("DYNAMISSCIENCE_DATA_ROOT", "")
    configured = configured.strip()
    if not configured:
        raise DataRootConfigurationError("Set DYNAMISSCIENCE_DATA_ROOT to a private directory")
    return _validate_root(Path(configured))


def ensure_layout(root: str | os.PathLike[str] | None = None) -> Path:
    base = data_root(root)
    base.mkdir(parents=True, exist_ok=True)
    for name in LAYOUT:
        (base / name).mkdir(parents=True, exist_ok=True)
    return base


def paths(root: str | os.PathLike[str] | None = None) -> dict[str, Path]:
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
