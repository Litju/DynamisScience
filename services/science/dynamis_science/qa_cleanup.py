"""Safety primitives for marked, disposable DynamisScience QA runs."""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MARKER_NAME = ".dynamisscience-qa-run.json"
LOCK_NAME = ".dynamisscience-qa-run.lock"
RUN_PREFIX = "dynamisscience-qa-"


class QaRunError(RuntimeError):
    """Raised when a QA run cannot be safely allocated or finalized."""


def resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _overlaps(first: Path, second: Path) -> bool:
    return first == second or first.is_relative_to(second) or second.is_relative_to(first)


def validate_scratch_parent(
    parent: str | Path,
    *,
    repository: str | Path,
    protected_roots: tuple[str | Path, ...],
) -> Path:
    raw_candidate = Path(parent).expanduser().absolute()
    candidate = raw_candidate.resolve(strict=False)
    if candidate == candidate.anchor or len(candidate.parts) < 3:
        raise QaRunError("Scratch parent is too broad; use a dedicated directory below a user temp root.")
    protected = (resolved(repository), *(resolved(path) for path in protected_roots))
    if any(_overlaps(candidate, path) for path in protected):
        raise QaRunError("Scratch parent overlaps the repository or a protected data root.")
    candidate.mkdir(parents=True, exist_ok=True)
    if raw_candidate.exists() and raw_candidate.is_symlink():
        raise QaRunError("Scratch parent cannot be a symbolic link.")
    return candidate


def tree_bytes(root: str | Path) -> int:
    """Measure regular files without following links outside a run root."""
    base = Path(root)
    total = 0
    for directory, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = [name for name in dirnames if not (Path(directory) / name).is_symlink()]
        for filename in filenames:
            path = Path(directory) / filename
            try:
                if path.is_symlink():
                    continue
                total += path.stat().st_size
            except FileNotFoundError:
                continue
    return total


def read_marker(root: str | Path) -> dict[str, Any]:
    raw_root = Path(root).expanduser().absolute()
    if raw_root.is_symlink():
        raise QaRunError("Run root cannot be a symbolic link.")
    run_root = raw_root.resolve(strict=True)
    marker_path = run_root / MARKER_NAME
    if not marker_path.is_file() or marker_path.is_symlink():
        raise QaRunError("Marked run metadata is missing or unsafe.")
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QaRunError("Marked run metadata cannot be read.") from exc
    run_id = marker.get("run_id")
    parent = Path(marker.get("scratch_parent", "")).resolve(strict=True)
    if not isinstance(run_id, str) or run_root.name != f"{RUN_PREFIX}{run_id}" or run_root.parent != parent:
        raise QaRunError("Run path does not match its ownership marker.")
    return marker


def write_marker(root: str | Path, marker: dict[str, Any]) -> None:
    run_root = Path(root)
    path = run_root / MARKER_NAME
    temporary = run_root / f"{MARKER_NAME}.tmp"
    payload = json.dumps(marker, sort_keys=True, indent=2)
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def allocate_run_root(
    parent: str | Path,
    *,
    repository: str | Path,
    protected_roots: tuple[str | Path, ...],
    issue_id: str,
    max_bytes: int,
    min_free_bytes: int,
) -> tuple[Path, dict[str, Any]]:
    if not issue_id.startswith("RES-") or not issue_id[4:].isdigit():
        raise QaRunError("A Linear issue ID such as RES-648 is required.")
    if max_bytes <= 0 or min_free_bytes < 0:
        raise QaRunError("Disk limits must be positive and include a non-negative free-space reserve.")
    scratch_parent = validate_scratch_parent(
        parent, repository=repository, protected_roots=protected_roots
    )
    free_start = shutil.disk_usage(scratch_parent).free
    if free_start - max_bytes < min_free_bytes:
        raise QaRunError(
            f"Insufficient scratch capacity: {free_start} free bytes, "
            f"{max_bytes} budget bytes, {min_free_bytes} required afterward."
        )
    run_id = uuid.uuid4().hex
    root = scratch_parent / f"{RUN_PREFIX}{run_id}"
    root.mkdir(mode=0o700)
    now = datetime.now(UTC).isoformat()
    marker: dict[str, Any] = {
        "schema": 1,
        "run_id": run_id,
        "issue_id": issue_id,
        "scratch_parent": str(scratch_parent),
        "repository": str(resolved(repository)),
        "protected_roots": [str(resolved(path)) for path in protected_roots],
        "owner_pid": os.getpid(),
        "created_at": now,
        "state": "ALLOCATED",
        "max_bytes": int(max_bytes),
        "min_free_bytes": int(min_free_bytes),
        "free_bytes_start": int(free_start),
        "peak_bytes": 0,
        "linear_recording_reference": None,
    }
    (root / LOCK_NAME).write_bytes(b"\0")
    write_marker(root, marker)
    return root, marker


def _try_lock(handle: Any) -> bool:
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(handle: Any) -> None:
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


class RunLock:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve(strict=True)
        self.handle: Any | None = None

    def __enter__(self) -> "RunLock":
        marker = read_marker(self.root)
        lock_path = self.root / LOCK_NAME
        if not lock_path.is_file() or lock_path.is_symlink():
            raise QaRunError("Run ownership lock is missing or unsafe.")
        self.handle = lock_path.open("r+b")
        if not _try_lock(self.handle):
            self.handle.close()
            self.handle = None
            raise QaRunError("Run root is active in another process.")
        # A live recorded owner is retained even when the advisory lock is free.
        owner_pid = marker.get("owner_pid")
        if isinstance(owner_pid, int) and owner_pid != os.getpid() and pid_is_alive(owner_pid):
            _unlock(self.handle)
            self.handle.close()
            self.handle = None
            raise QaRunError("Recorded run owner is still active; refusing cleanup.")
        return self

    def __exit__(self, *_exc: object) -> None:
        if self.handle is not None:
            _unlock(self.handle)
            self.handle.close()
            self.handle = None


def pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def stale_run_roots(parent: str | Path, *, older_than_seconds: int) -> list[Path]:
    """List old, marked roots whose ownership lock and recorded process are inactive."""
    root_parent = Path(parent).resolve(strict=True)
    now = time.time()
    stale: list[Path] = []
    for candidate in root_parent.iterdir():
        if not candidate.is_dir() or candidate.is_symlink() or not candidate.name.startswith(RUN_PREFIX):
            continue
        try:
            marker = read_marker(candidate)
            created = datetime.fromisoformat(marker["created_at"].replace("Z", "+00:00")).timestamp()
            if now - created < older_than_seconds:
                continue
            if pid_is_alive(int(marker.get("owner_pid", -1))):
                continue
            with candidate.joinpath(LOCK_NAME).open("r+b") as lock_handle:
                if not _try_lock(lock_handle):
                    continue
                _unlock(lock_handle)
            stale.append(candidate)
        except (OSError, KeyError, TypeError, ValueError, QaRunError):
            continue
    return stale


def purge_run_root(root: str | Path, *, issue_id: str, linear_recording_reference: str) -> dict[str, Any]:
    if not linear_recording_reference.strip():
        raise QaRunError("A Linear comment or document reference is required before purge.")
    run_root = Path(root).resolve(strict=True)
    marker = read_marker(run_root)
    if marker.get("issue_id") != issue_id:
        raise QaRunError("Issue ID does not match the run ownership marker.")
    if marker.get("state") not in {"AWAITING_LINEAR_RECORD", "ABANDONED"}:
        raise QaRunError("Only a completed or recovered run can be purged.")
    with RunLock(run_root):
        marker = read_marker(run_root)
        marker["linear_recording_reference"] = linear_recording_reference.strip()
        marker["purge_started_at"] = datetime.now(UTC).isoformat()
        write_marker(run_root, marker)
        bytes_reclaimed = tree_bytes(run_root)
        free_before = shutil.disk_usage(run_root.parent).free
        parent = run_root.parent.resolve(strict=True)
        if run_root.parent != parent or run_root.name != f"{RUN_PREFIX}{marker['run_id']}":
            raise QaRunError("Run root changed identity before purge.")
        if _overlaps(run_root, Path(marker["repository"]).resolve(strict=True)):
            raise QaRunError("Run root overlaps the canonical repository.")
        if any(_overlaps(run_root, Path(item).resolve(strict=False)) for item in marker["protected_roots"]):
            raise QaRunError("Run root overlaps a protected data root.")
        # Raise through the context so its handle releases the lock before deletion.
        raise _PurgeAfterLock(run_root, bytes_reclaimed, free_before)


class _PurgeAfterLock(Exception):
    """Private control flow used to release the advisory lock before deleting the tree."""

    def __init__(self, root: Path, bytes_reclaimed: int, free_before: int):
        self.root = root
        self.bytes_reclaimed = bytes_reclaimed
        self.free_before = free_before


def finalize_purge(root: str | Path, *, issue_id: str, linear_recording_reference: str) -> dict[str, Any]:
    try:
        return purge_run_root(
            root, issue_id=issue_id, linear_recording_reference=linear_recording_reference
        )
    except _PurgeAfterLock as pending:
        # The exception is raised inside the RunLock context and reaches here after __exit__ released it.
        try:
            shutil.rmtree(pending.root)
        except OSError as exc:
            free_after = shutil.disk_usage(pending.root.parent).free
            return {
                "run_root": str(pending.root),
                "issue_id": issue_id,
                "bytes_reclaimed": max(0, free_after - pending.free_before),
                "bytes_retained": tree_bytes(pending.root) if pending.root.exists() else 0,
                "free_bytes_before_purge": pending.free_before,
                "free_bytes_after_purge": free_after,
                "linear_recording_reference": linear_recording_reference.strip(),
                "leftover_path": str(pending.root) if pending.root.exists() else None,
                "cleanup_error": f"{type(exc).__name__}: {exc}",
            }
        parent = pending.root.parent
        free_after = shutil.disk_usage(parent).free
        return {
            "run_root": str(pending.root),
            "issue_id": issue_id,
            "bytes_reclaimed": max(0, free_after - pending.free_before),
            "bytes_removed_from_tree": pending.bytes_reclaimed,
            "bytes_retained": 0,
            "free_bytes_before_purge": pending.free_before,
            "free_bytes_after_purge": free_after,
            "linear_recording_reference": linear_recording_reference.strip(),
            "leftover_path": None,
        }
