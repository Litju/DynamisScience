from __future__ import annotations

import hashlib
import sqlite3

import pytest

from dynamis_science import importer, researchstore, researchanalysis
from dynamis_science.desktop.services import DynamisAppService
from test_importer import FIXTURE, HEADER, _ready


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    app = DynamisAppService()
    app.ensure_initialized()
    return app


def batch(tmp_path, number, context=None):
    file = tmp_path / f"batch{number}.csv"
    file.write_text(HEADER.strip() + ",week\n" + f"A1,T{number}a,{39+number},80,1800,{number}\nA2,T{number}b,{37+number},75,1700,{number}\n")
    staged = importer.stage(_ready(file, week=number), context or importer.build_context(FIXTURE))
    assert staged["eligible"], staged
    return importer.admit(staged)["dataset_snapshot_id"]


def run(service, identity, revision):
    return service.execute_analysis_run(identity, {"method_id": "METH-U-DESC", "outcome_metric_id": "MET-CMJ-HEIGHT",
                                                  "parameters": {}, "data_revision_id": revision})


def test_workspace_empty_attach_analyze_append_export_reopen(service, tmp_path):
    empty = service.create_workspace("Continuing investigation")
    identity = empty["study"]["id"]
    assert not empty["study"]["dataset_snapshot_id"]
    assert not service.list_cohorts(identity) and not service.list_plans(identity)
    assert service.get_study_detail(identity)["study"]["id"] == identity
    context = importer.build_context(FIXTURE)
    one = batch(tmp_path, 1, context)
    detail = service.attach_workspace_data(identity, one)
    rev1 = detail["active_data_revision_id"]
    first = run(service, identity, rev1)
    first_report = service.export_workspace_report(identity, first["id"], str(tmp_path / "first.html"))
    assert first["id"] in first_report.read_text()
    original_html = first_report.read_bytes()
    original_run = researchstore.get_run(first["id"])
    two = batch(tmp_path, 2, context)
    current = service.attach_workspace_data(identity, two, append=True, confirm_participant_ids=True, base_revision=rev1)
    rev2 = current["active_data_revision_id"]
    assert rev1 != rev2 and current["study"]["id"] == identity
    assert researchstore.read_snapshot_table(current["snapshot"]["id"], "cmj_trials").height == 4
    second = run(service, identity, rev2)
    second_report = service.export_workspace_report(identity, second["id"], str(tmp_path / "second.html"))
    assert second["id"] in second_report.read_text()
    assert first_report.read_bytes() == original_html
    assert researchstore.get_run(first["id"]) == original_run
    reopened = DynamisAppService().get_study_detail(identity)
    assert reopened["active_data_revision_id"] == rev2
    assert len(reopened["data_revisions"]) == 2 and len(reopened["runs"]) == 2
    versions = [researchstore.get_report_version(identity, item["version"]) for item in sorted(researchstore.report_versions(identity), key=lambda item: item["version"])]
    assert len(versions) == 2
    assert versions[0]["frozen_content"]["data_revision"]["id"] == rev1
    assert versions[1]["frozen_content"]["data_revision"]["id"] == rev2
    assert versions[1]["frozen_content"]["evidence"][0]["analysis_run_id"] == second["id"]
    historical = researchstore.select_data_revision(identity, rev1)
    assert historical["snapshot"]["id"] == one
    assert historical["current_plan"]["id"] == first["plan_id"]


def test_failures_rollback_and_separate_attachments(service, tmp_path, monkeypatch):
    identity = service.create_workspace("Separate")['study']['id']
    one = batch(tmp_path, 1)
    rev1 = service.attach_workspace_data(identity, one)["active_data_revision_id"]
    before = researchstore.get_entity(identity)
    with pytest.raises(researchstore.ResearchValidation):
        service.attach_workspace_data(identity, "missing", base_revision=rev1)
    with pytest.raises(researchstore.ResearchValidation):
        service.attach_workspace_data(identity, one, append=True, base_revision=rev1)
    two = batch(tmp_path, 2, importer.build_context({**FIXTURE, "source_name": "Unrelated lab", "dataset_identity": "different"}))
    with pytest.raises(researchstore.ResearchValidation, match="Incompatible"):
        service.attach_workspace_data(identity, two, append=True, confirm_participant_ids=True, base_revision=rev1)
    assert researchstore.get_entity(identity) == before
    audit = researchstore._audit
    def fail(*args, **kwargs):
        raise RuntimeError("Injected write failure")
    monkeypatch.setattr(researchstore, "_audit", fail)
    with pytest.raises(RuntimeError):
        service.attach_workspace_data(identity, two, base_revision=rev1)
    assert researchstore.get_entity(identity) == before and len(researchstore.data_revisions(identity)) == 1
    monkeypatch.setattr(researchstore, "_audit", audit)
    rev2 = service.attach_workspace_data(identity, two, base_revision=rev1)["active_data_revision_id"]
    assert researchstore.get_data_revision(rev2)["input_snapshot_ids"] == [two]
    with pytest.raises(researchstore.ResearchConflict):
        run(service, identity, rev1)


def test_inflight_analysis_keeps_captured_revision(service, tmp_path, monkeypatch):
    identity = service.create_workspace("In flight")["study"]["id"]
    one, two = batch(tmp_path, 1), batch(tmp_path, 2)
    rev1 = service.attach_workspace_data(identity, one)["active_data_revision_id"]
    execute = researchanalysis.execute
    def concurrent(entity, *args, **kwargs):
        service.attach_workspace_data(identity, two, base_revision=rev1)
        return execute(entity, *args, **kwargs)
    monkeypatch.setattr(researchanalysis, "execute", concurrent)
    saved = run(service, identity, rev1)
    assert saved["data_revision_id"] == rev1 and saved["snapshot_id"] == one
    assert service.get_study_detail(identity)["active_data_revision_id"] != rev1
    with pytest.raises(researchstore.ResearchConflict):
        service.export_workspace_report(identity, saved["id"], str(tmp_path / "stale.html"))


def test_additive_migration_repeatable(service):
    identity = service.create_workspace("Migration")["study"]["id"]
    with researchstore._connect() as connection:
        connection.execute("PRAGMA user_version=1")
    assert service.get_study_detail(identity)["study"]["id"] == identity
    with researchstore._connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
