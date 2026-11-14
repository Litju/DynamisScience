"""Run one disk-bounded QA command and retain its log only until Linear records it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = SERVICE_ROOT.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SERVICE_ROOT))

from dynamis_science.qa_cleanup import (  # noqa: E402
    LOCK_NAME,
    MARKER_NAME,
    RUN_PREFIX,
    QaRunError,
    RunLock,
    allocate_run_root,
    finalize_purge,
    read_marker,
    stale_run_roots,
    tree_bytes,
    validate_scratch_parent,
    write_marker,
)

DEFAULT_DATASET_ROOT = Path(r"D:\datasets\DynamisScience")
MIB = 1024 * 1024


def _git(*args: str, cwd: Path = REPOSITORY_ROOT) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=False
    )
    if completed.returncode:
        raise QaRunError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def _source_state() -> dict[str, Any]:
    changed: dict[str, str] = {}
    status = _git("status", "--porcelain", "--untracked-files=all")
    for line in status.splitlines():
        relative = line[3:]
        if " -> " in relative:
            relative = relative.rsplit(" -> ", 1)[-1]
        path = REPOSITORY_ROOT / relative
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(8 * MIB), b""):
                    digest.update(chunk)
            changed[relative] = digest.hexdigest()
    return {
        "head": _git("rev-parse", "HEAD"),
        "status": status,
        "changed_file_sha256": changed,
    }


def _worktree_snapshot() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    blocks = _git("worktree", "list", "--porcelain").split("\n\n")
    for block in blocks:
        fields: dict[str, str] = {}
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            fields[key] = value
        path = fields.get("worktree")
        if not path:
            continue
        entry: dict[str, Any] = {
            "path": path,
            "head": fields.get("HEAD"),
            "branch": fields.get("branch"),
            "primary": Path(path).resolve() == REPOSITORY_ROOT.resolve(),
            "detached": "detached" in fields,
        }
        if Path(path).is_dir():
            result = subprocess.run(
                ["git", "-C", path, "status", "--porcelain", "--untracked-files=all"],
                text=True,
                capture_output=True,
                check=False,
            )
            entry["status"] = "clean" if result.returncode == 0 and not result.stdout.strip() else "dirty-or-unknown"
        else:
            entry["status"] = "missing"
        # Worktrees not created and registered by this run are intentionally retained.
        entry["cleanup"] = "retained: not created by this run"
        records.append(entry)
    return records


def _hash_tree(root: Path) -> tuple[int, int, str]:
    file_count = 0
    byte_count = 0
    aggregate = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise QaRunError(f"Research source contains a symbolic link: {path}")
        if not path.is_file():
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(8 * MIB), b""):
                digest.update(chunk)
        size = path.stat().st_size
        relative = path.relative_to(root).as_posix()
        aggregate.update(f"{relative}\0{size}\0{digest.hexdigest()}\n".encode("utf-8"))
        file_count += 1
        byte_count += size
    return file_count, byte_count, aggregate.hexdigest()


def _copy_source(source: Path, destination: Path) -> dict[str, Any]:
    if not source.is_dir() or source.is_symlink():
        raise QaRunError("The authorized test source root is missing or unsafe.")
    if tree_bytes(source) > shutil.disk_usage(destination.parent).free:
        raise QaRunError("Insufficient free space for one disposable research source copy.")
    shutil.copytree(source, destination, symlinks=False)
    source_count, source_bytes, source_hash = _hash_tree(source)
    copy_count, copy_bytes, copy_hash = _hash_tree(destination)
    if (source_count, source_bytes, source_hash) != (copy_count, copy_bytes, copy_hash):
        raise QaRunError("Disposable research source copy failed full file-hash verification.")
    return {"file_count": source_count, "bytes": source_bytes, "tree_sha256": source_hash}


def _terminate_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except OSError:
            process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _command_with_pytest_scratch(command: list[str], run_root: Path) -> list[str]:
    if any("pytest" in Path(item).name.lower() or item.lower() == "pytest" for item in command):
        if not any(item == "--basetemp" or item.startswith("--basetemp=") for item in command):
            command = [*command, "--basetemp", str(run_root / "pytest-basetemp")]
        if not any(item == "-o" and index + 1 < len(command) and command[index + 1].startswith("cache_dir=") for index, item in enumerate(command)):
            command = [*command, "-o", f"cache_dir={run_root / 'pytest-cache'}"]
    return command


def _pytest_summary(log_path: Path) -> dict[str, int] | None:
    if not log_path.is_file():
        return None
    text = log_path.read_text(encoding="utf-8", errors="replace")[-16_384:]
    summary: dict[str, int] = {}
    for key in ("passed", "failed", "skipped", "errors", "xfailed", "xpassed", "deselected"):
        matches = re.findall(rf"\b(\d+)\s+{key}\b", text)
        if matches:
            summary[key] = int(matches[-1])
    return summary or None


def run_command(args: argparse.Namespace) -> int:
    if not args.command:
        raise QaRunError("Pass a command after `--`.")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise QaRunError("Pass a command after `--`.")
    cwd = Path(args.cwd).resolve() if args.cwd else SERVICE_ROOT.resolve()
    if not cwd.is_relative_to(REPOSITORY_ROOT.resolve()):
        raise QaRunError("QA commands must run from the canonical repository.")
    dataset_root = Path(args.dataset_root).resolve()
    scratch_parent = validate_scratch_parent(
        args.scratch_parent,
        repository=REPOSITORY_ROOT,
        protected_roots=(dataset_root,),
    )
    stale = stale_run_roots(scratch_parent, older_than_seconds=args.stale_after_minutes * 60)
    if stale:
        paths = ", ".join(str(path) for path in stale)
        raise QaRunError(
            "Abandoned marked scratch needs review before a new run: " + paths +
            ". Use `recover`, inspect/record each result in Linear, then `purge`."
        )
    run_root, marker = allocate_run_root(
        scratch_parent,
        repository=REPOSITORY_ROOT,
        protected_roots=(dataset_root,),
        issue_id=args.issue,
        max_bytes=args.max_scratch_mib * MIB,
        min_free_bytes=args.min_free_mib * MIB,
    )
    log_path = run_root / "run.log"
    marker.update(
        {
            "state": "RUNNING",
            "command": command,
            "cwd": str(cwd),
            "started_at": datetime.now(UTC).isoformat(),
            "log_path": str(log_path),
            "runner_pid": os.getpid(),
            "source_state": _source_state(),
            "initial_scratch_bytes": tree_bytes(run_root),
            "source_copy": None,
        }
    )
    child_env = os.environ.copy()
    for key, value in {
        "TEMP": str(run_root),
        "TMP": str(run_root),
        "TMPDIR": str(run_root),
        "PYTHONPYCACHEPREFIX": str(run_root / "pycache"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "UV_PROJECT_ENVIRONMENT": str(run_root / "venv"),
        "UV_CACHE_DIR": str(run_root / "uv-cache"),
        "MPLCONFIGDIR": str(run_root / "matplotlib"),
        "XDG_CACHE_HOME": str(run_root / "cache"),
        "DYNAMISSCIENCE_QA_RUN_ROOT": str(run_root),
        "DYNAMISSCIENCE_QA_RUN_ID": marker["run_id"],
        "DYNAMISSCIENCE_QA_ISSUE_ID": args.issue,
    }.items():
        child_env[key] = value
    if args.copy_source:
        source_copy = run_root / "research-source"
        try:
            source_bytes = tree_bytes(dataset_root)
            if source_bytes > marker["max_bytes"] - tree_bytes(run_root):
                raise QaRunError(
                    f"Source copy needs {source_bytes} bytes, beyond remaining run budget."
                )
            marker["source_copy"] = _copy_source(dataset_root, source_copy)
            child_env["DYNAMISSCIENCE_TEST_SOURCE_ROOT"] = str(source_copy)
        except Exception as exc:
            marker["setup_error"] = f"{type(exc).__name__}: {exc}"
            marker["state"] = "AWAITING_LINEAR_RECORD"
            marker["exit_code"] = 125
            marker["finished_at"] = datetime.now(UTC).isoformat()
            marker["peak_bytes"] = tree_bytes(run_root)
            marker["bytes_reclaimable"] = marker["peak_bytes"]
            marker["free_bytes_end_before_purge"] = shutil.disk_usage(run_root).free
            write_marker(run_root, marker)
            print(json.dumps(_summary(marker, run_root), indent=2))
            return 125
    else:
        child_env.pop("DYNAMISSCIENCE_TEST_SOURCE_ROOT", None)
    child_command = _command_with_pytest_scratch(command, run_root)
    if args.copy_source:
        marker["source_copy"] = marker.get("source_copy")
    write_marker(run_root, marker)
    return_code = 127
    peak = tree_bytes(run_root)
    budget_reason: str | None = None
    spawn_error: str | None = None
    started = time.monotonic()
    process: subprocess.Popen[bytes] | None = None
    try:
        with RunLock(run_root), log_path.open("wb") as log:
            try:
                flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
                process = subprocess.Popen(
                    child_command,
                    cwd=cwd,
                    env=child_env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    shell=False,
                    creationflags=flags,
                    start_new_session=os.name != "nt",
                )
                marker["child_pid"] = process.pid
                write_marker(run_root, marker)
                while process.poll() is None:
                    time.sleep(0.25)
                    current = tree_bytes(run_root)
                    peak = max(peak, current)
                    free_now = shutil.disk_usage(run_root).free
                    if current > marker["max_bytes"]:
                        budget_reason = f"scratch usage {current} exceeded budget {marker['max_bytes']}"
                        _terminate_tree(process)
                        break
                    if free_now < marker["min_free_bytes"]:
                        budget_reason = f"free space {free_now} fell below reserve {marker['min_free_bytes']}"
                        _terminate_tree(process)
                        break
                    if args.timeout_seconds and time.monotonic() - started > args.timeout_seconds:
                        budget_reason = f"run exceeded timeout {args.timeout_seconds}s"
                        _terminate_tree(process)
                        break
                return_code = process.wait()
            except OSError as exc:
                spawn_error = f"{type(exc).__name__}: {exc}"
                return_code = 127
            except KeyboardInterrupt:
                if process is not None:
                    child_return_code = process.poll()
                    if child_return_code is None:
                        _terminate_tree(process)
                        return_code = process.returncode if process.returncode is not None else 130
                        if return_code == 0:
                            marker["interrupt_raced_with_clean_child_exit"] = True
                        else:
                            budget_reason = "SIGINT received while command was still active"
                    else:
                        return_code = child_return_code
                        marker["interrupt_received_after_child_exit"] = True
                else:
                    return_code = 130
                    budget_reason = "SIGINT received before command started"
            log.flush()
            os.fsync(log.fileno())
        peak = max(peak, tree_bytes(run_root))
        log_hash = hashlib.sha256(log_path.read_bytes()).hexdigest() if log_path.exists() else None
        marker.update(
            {
                "state": "AWAITING_LINEAR_RECORD",
                "finished_at": datetime.now(UTC).isoformat(),
                "exit_code": int(return_code),
                "spawn_error": spawn_error,
                "stop_reason": budget_reason,
                "duration_seconds": round(time.monotonic() - started, 3),
                "peak_bytes": int(peak),
                "bytes_reclaimable": int(tree_bytes(run_root)),
                "free_bytes_end_before_purge": int(shutil.disk_usage(run_root).free),
                "log_sha256": log_hash,
                "test_summary": _pytest_summary(log_path),
                "worktrees": _worktree_snapshot(),
            }
        )
        write_marker(run_root, marker)
        print(json.dumps(_summary(marker, run_root), indent=2))
        return return_code if budget_reason is None else (return_code or 124)
    except Exception:
        # Preserve a marked failure for its compact Linear disposition and guarded purge.
        marker.update(
            {
                "state": "AWAITING_LINEAR_RECORD",
                "finished_at": datetime.now(UTC).isoformat(),
                "exit_code": int(return_code),
                "stop_reason": "runner exception; inspect run.log",
                "peak_bytes": max(peak, tree_bytes(run_root)),
                "bytes_reclaimable": tree_bytes(run_root),
                "free_bytes_end_before_purge": shutil.disk_usage(run_root).free,
            }
        )
        write_marker(run_root, marker)
        print(json.dumps(_summary(marker, run_root), indent=2))
        raise


def _summary(marker: dict[str, Any], run_root: Path) -> dict[str, Any]:
    source_state = marker.get("source_state") or _source_state()
    return {
        "issue_id": marker["issue_id"],
        "run_id": marker["run_id"],
        "state": marker["state"],
        "source_commit": source_state["head"],
        "source_state": source_state,
        "command": marker.get("command"),
        "exit_code": marker.get("exit_code"),
        "test_summary": marker.get("test_summary"),
        "stop_reason": marker.get("stop_reason") or marker.get("setup_error"),
        "interrupt_raced_with_clean_child_exit": marker.get("interrupt_raced_with_clean_child_exit", False),
        "duration_seconds": marker.get("duration_seconds"),
        "scratch_root": str(run_root),
        "scratch_peak_bytes_sampled": marker.get("peak_bytes"),
        "bytes_created": max(0, marker.get("peak_bytes", 0) - marker.get("initial_scratch_bytes", 0)),
        "bytes_reclaimable": marker.get("bytes_reclaimable", tree_bytes(run_root)),
        "free_bytes_start": marker.get("free_bytes_start"),
        "free_bytes_end_before_purge": marker.get("free_bytes_end_before_purge"),
        "source_copy": marker.get("source_copy"),
        "log_sha256": marker.get("log_sha256"),
        "log_path": marker.get("log_path"),
        "worktrees": marker.get("worktrees", _worktree_snapshot()),
        "linear_record_required_before_purge": True,
        "owner_data_root_mutated": False,
    }


def recover(args: argparse.Namespace) -> int:
    roots = stale_run_roots(args.scratch_parent, older_than_seconds=args.older_than_minutes * 60)
    records = []
    for root in roots:
        marker = read_marker(root)
        marker["state"] = "ABANDONED"
        marker["abandoned_detected_at"] = datetime.now(UTC).isoformat()
        write_marker(root, marker)
        records.append(
            {
                "run_id": marker["run_id"],
                "issue_id": marker.get("issue_id"),
                "scratch_root": str(root),
                "state": marker["state"],
                "bytes_reclaimable": tree_bytes(root),
                "exit_code": marker.get("exit_code"),
                "log_path": marker.get("log_path"),
                "action": "retained until findings are recorded in Linear",
            }
        )
    print(json.dumps({"stale_runs": records}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    run = subparsers.add_parser("run", help="allocate, run, measure, and retain until Linear closeout")
    run.add_argument("--issue", required=True)
    run.add_argument("--scratch-parent", default=str(Path(os.environ.get("TEMP", str(Path.home()))) / "dynamisscience-qa"))
    run.add_argument("--dataset-root", default=os.environ.get("DYNAMISSCIENCE_DATA_ROOT", str(DEFAULT_DATASET_ROOT)))
    run.add_argument("--cwd")
    run.add_argument("--copy-source", action="store_true", help="copy and hash-verify the authorized private research source")
    run.add_argument("--max-scratch-mib", type=int, default=16 * 1024)
    run.add_argument("--min-free-mib", type=int, default=12 * 1024)
    run.add_argument("--timeout-seconds", type=int, default=0)
    run.add_argument("--stale-after-minutes", type=int, default=30)
    run.add_argument("command", nargs=argparse.REMAINDER)
    run.set_defaults(handler=run_command)

    purge = subparsers.add_parser("purge", help="purge one completed run after a Linear record exists")
    purge.add_argument("--run-root", required=True)
    purge.add_argument("--issue", required=True)
    purge.add_argument("--linear-reference", required=True)
    purge.set_defaults(handler=purge_command)

    stale = subparsers.add_parser("recover", help="list safe-to-review marked roots left by crashed runs")
    stale.add_argument("--scratch-parent", required=True)
    stale.add_argument("--older-than-minutes", type=int, default=30)
    stale.set_defaults(handler=recover)
    return parser


def purge_command(args: argparse.Namespace) -> int:
    result = finalize_purge(
        args.run_root,
        issue_id=args.issue,
        linear_recording_reference=args.linear_reference,
    )
    print(json.dumps(result, indent=2))
    return 1 if result.get("leftover_path") else 0


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = args.handler(args)
        return int(result or 0)
    except QaRunError as exc:
        print(json.dumps({"error": str(exc), "safe_to_continue": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
