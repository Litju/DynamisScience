from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from dynamis_science import qa_cleanup


def _allocate(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    repository = tmp_path / "repo"
    dataset = tmp_path / "dataset"
    repository.mkdir()
    dataset.mkdir()
    return qa_cleanup.allocate_run_root(
        tmp_path / "scratch",
        repository=repository,
        protected_roots=(dataset,),
        issue_id="RES-648",
        max_bytes=1024 * 1024,
        min_free_bytes=0,
    )


def test_run_root_is_marked_and_lives_outside_protected_roots(tmp_path):
    root, marker = _allocate(tmp_path)

    assert root.parent == (tmp_path / "scratch").resolve()
    assert root.name == f"{qa_cleanup.RUN_PREFIX}{marker['run_id']}"
    assert qa_cleanup.read_marker(root)["issue_id"] == "RES-648"
    assert qa_cleanup.tree_bytes(root) > 0


@pytest.mark.parametrize("protected", ["repository", "dataset"])
def test_scratch_parent_cannot_overlap_protected_roots(tmp_path, protected):
    repo = tmp_path / "repo"
    dataset = tmp_path / "dataset"
    repo.mkdir()
    dataset.mkdir()
    candidate = repo if protected == "repository" else dataset

    with pytest.raises(qa_cleanup.QaRunError, match="overlaps"):
        qa_cleanup.validate_scratch_parent(
            candidate, repository=repo, protected_roots=(dataset,)
        )


def test_capacity_preflight_refuses_budget_that_breaks_free_space_reserve(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    dataset = tmp_path / "dataset"
    repo.mkdir()
    dataset.mkdir()
    monkeypatch.setattr(
        qa_cleanup.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=100, used=20, free=80),
    )

    with pytest.raises(qa_cleanup.QaRunError, match="Insufficient scratch capacity"):
        qa_cleanup.allocate_run_root(
            tmp_path / "scratch",
            repository=repo,
            protected_roots=(dataset,),
            issue_id="RES-648",
            max_bytes=60,
            min_free_bytes=30,
        )


def test_stale_inventory_requires_old_marker_dead_owner_and_free_lock(tmp_path):
    root, marker = _allocate(tmp_path)
    marker["owner_pid"] = 2_147_483_647
    marker["created_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    qa_cleanup.write_marker(root, marker)

    assert qa_cleanup.stale_run_roots(root.parent, older_than_seconds=60) == [root]


def test_stale_inventory_retains_a_live_owner(tmp_path):
    root, marker = _allocate(tmp_path)
    marker["created_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    qa_cleanup.write_marker(root, marker)

    assert qa_cleanup.stale_run_roots(root.parent, older_than_seconds=60) == []


def test_run_lock_refuses_an_active_lock(tmp_path, monkeypatch):
    root, _marker = _allocate(tmp_path)
    monkeypatch.setattr(qa_cleanup, "_try_lock", lambda _handle: False)

    with pytest.raises(qa_cleanup.QaRunError, match="active"):
        with qa_cleanup.RunLock(root):
            pass


def test_run_lock_refuses_a_live_recorded_owner(tmp_path, monkeypatch):
    root, marker = _allocate(tmp_path)
    marker["owner_pid"] = 2_147_483_646
    qa_cleanup.write_marker(root, marker)
    monkeypatch.setattr(qa_cleanup, "pid_is_alive", lambda _pid: True)

    with pytest.raises(qa_cleanup.QaRunError, match="still active"):
        with qa_cleanup.RunLock(root):
            pass


def test_purge_requires_issue_and_linear_record_reference(tmp_path):
    root, marker = _allocate(tmp_path)
    marker["state"] = "AWAITING_LINEAR_RECORD"
    qa_cleanup.write_marker(root, marker)

    with pytest.raises(qa_cleanup.QaRunError, match="Linear"):
        qa_cleanup.finalize_purge(
            root, issue_id="RES-648", linear_recording_reference=" "
        )
    with pytest.raises(qa_cleanup.QaRunError, match="does not match"):
        qa_cleanup.finalize_purge(
            root, issue_id="RES-613", linear_recording_reference="comment-id"
        )

    result = qa_cleanup.finalize_purge(
        root, issue_id="RES-648", linear_recording_reference="comment-id"
    )

    assert result["bytes_removed_from_tree"] > 0
    assert result["bytes_retained"] == 0
    assert result["linear_recording_reference"] == "comment-id"
    assert not root.exists()


def test_unmarked_directory_cannot_be_purged(tmp_path):
    target = tmp_path / "dynamisscience-qa-unmarked"
    target.mkdir()

    with pytest.raises(qa_cleanup.QaRunError, match="metadata"):
        qa_cleanup.finalize_purge(
            target, issue_id="RES-648", linear_recording_reference="comment-id"
        )

