from __future__ import annotations

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
    researchstore.update_entity(identity, {"design": "DESCRIPTIVE"})
    historical = researchstore.select_data_revision(identity, rev1)
    assert historical["study"]["design_code"] == "OBSERVATIONAL_LONGITUDINAL"
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
    original = researchstore.get_snapshot(one)
    with pytest.raises(researchstore.ResearchValidation, match="calibration"):
        researchstore._validate_workspace_append([original, {**original, "provenance": {**original["provenance"], "instrument_metadata": [{"calibration": "CHANGED"}]}}])
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


def test_missing_time_metadata_is_rejected_before_saving_analysis_context(service, tmp_path):
    identity = service.create_workspace("Missing axis")["study"]["id"]
    file = tmp_path / "no-axis.csv"
    file.write_text(HEADER + "A1,T1,40,80,1800\nA2,T2,39,75,1700\n")
    snapshot = importer.admit(importer.stage(_ready(file), importer.build_context(FIXTURE)))["dataset_snapshot_id"]
    revision = service.attach_workspace_data(identity, snapshot)["active_data_revision_id"]
    detail = service.get_study_detail(identity)
    assert any("Missing week" in issue for method in detail["eligibility"] for issue in method["issues"])
    with pytest.raises(researchstore.ResearchValidation, match="Missing week"):
        run(service, identity, revision)
    assert not researchstore.list_cohorts(identity) and not researchstore.list_plans(identity)
    assert not researchstore.list_runs(identity)


def test_report_freeze_failure_rolls_back_and_historical_export_ignores_current_data(service, tmp_path, monkeypatch):
    identity = service.create_workspace("Export transaction")["study"]["id"]
    revision = service.attach_workspace_data(identity, batch(tmp_path, 1))["active_data_revision_id"]
    saved = run(service, identity, revision)
    with monkeypatch.context() as patch:
        patch.setattr(researchstore, "get_run", lambda _: {**saved, "plan_alignment": "EXPLORATORY"})
        with pytest.raises(researchstore.ResearchValidation, match="Exploratory"):
            service.export_workspace_report(identity, saved["id"], str(tmp_path / "exploratory.html"))
    assert not researchstore.list_evidence(identity)
    freeze = researchstore.freeze_report
    def failure(*args):
        raise RuntimeError("Injected freeze failure")
    monkeypatch.setattr(researchstore, "freeze_report", failure)
    with pytest.raises(RuntimeError):
        service.export_workspace_report(identity, saved["id"], str(tmp_path / "failed.html"))
    assert not researchstore.list_evidence(identity) and not researchstore.report_versions(identity)
    monkeypatch.setattr(researchstore, "freeze_report", freeze)
    exported = service.export_workspace_report(identity, saved["id"], str(tmp_path / "saved.html"))
    version = researchstore.report_versions(identity)[0]["version"]
    original = exported.read_text(encoding="utf-8")
    monkeypatch.setattr(researchstore, "report_payload", failure)
    assert researchstore.export_html(identity, version) == original


def test_workspace_native_controls_and_stale_completion(service, tmp_path, qtbot, monkeypatch):
    from dynamis_science.desktop.main_window import MainWindow

    window = MainWindow(service)
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)
    empty = service.create_workspace("Native context")
    identity = empty["study"]["id"]
    window._show_study(identity, empty)
    qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)
    assert window.current_study_id == identity and not window.current_snapshot_id
    assert not window.research.execute_button.isEnabled()
    first, second = batch(tmp_path, 1), batch(tmp_path, 2)
    detail = service.attach_workspace_data(identity, first)
    rev1 = detail["active_data_revision_id"]
    saved = run(service, identity, rev1)
    current = service.attach_workspace_data(identity, second, base_revision=rev1)
    window._show_study(identity, current)
    qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)
    assert window.research.parameters.isHidden()
    assert window.research.latest_run is None
    window.research._run_completed(identity, saved)
    assert window.research.latest_run is None
    window._show_study(identity, researchstore.select_data_revision(identity, rev1))
    qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)
    assert window.research.latest_run["id"] == saved["id"]
    assert window.current_study_id == identity
    from dynamis_science.desktop.workbench.spec import AnalysisSpec
    callbacks = []
    rendered = []
    monkeypatch.setattr(window.runner, "submit", lambda operation, finish, failed: callbacks.append(finish))
    monkeypatch.setattr(window.results_doc, "show_blocks", lambda *args: rendered.append(args))
    spec = AnalysisSpec("descriptives", {"outcome": ["jump_height_cm"]}, snapshot_id=first, table="cmj_trials")
    window._run_descriptive(spec)
    window.current_study["active_data_revision_id"] = "CHANGED"
    callbacks[0](None)
    assert not rendered
    window.close()


@pytest.mark.parametrize("failure_at", ["parquet", "transaction"])
def test_failed_append_removes_only_uncommitted_derived_data(service, tmp_path, monkeypatch, failure_at):
    identity = service.create_workspace("Atomic append")["study"]["id"]
    context = importer.build_context(FIXTURE)
    first, second, third = [batch(tmp_path, n, context) for n in (1, 2, 3)]
    rev1 = service.attach_workspace_data(identity, first)["active_data_revision_id"]
    rev2 = service.attach_workspace_data(identity, second, append=True,
        confirm_participant_ids=True, base_revision=rev1)["active_data_revision_id"]
    directory = researchstore.paths()["research"] / "data"
    retained = {p: p.read_bytes() for p in directory.rglob("*.parquet")}
    before = researchstore.get_entity(identity)
    def fail(*args, **kwargs):
        raise RuntimeError("Injected append failure")
    with monkeypatch.context() as patch:
        if failure_at == "parquet":
            patch.setattr(researchstore.pl.DataFrame, "write_parquet", fail)
        else:
            patch.setattr(researchstore, "_audit", fail)
        with pytest.raises(RuntimeError, match="Injected"):
            service.attach_workspace_data(identity, third, append=True,
                confirm_participant_ids=True, base_revision=rev2)
    assert researchstore.get_entity(identity) == before
    assert [p.name for p in directory.iterdir()] == [rev2]
    assert all(p.read_bytes() == content for p, content in retained.items())
    assert len(researchstore.data_revisions(identity)) == 2
    rev3 = service.attach_workspace_data(identity, third, append=True,
        confirm_participant_ids=True, base_revision=rev2)["active_data_revision_id"]
    assert researchstore.read_snapshot_table(rev3, "cmj_trials").height == 6


@pytest.mark.parametrize("break_migration", [False, True])
def test_real_v1_schema_upgrade_is_additive_and_rollback_safe(service, monkeypatch, break_migration):
    import sqlite3
    project = researchstore.create_project("Legacy retained")
    database = researchstore._db_path()
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE workspace_revisions")
        connection.execute("PRAGMA user_version=1")
        before = connection.execute("SELECT document FROM projects WHERE id=?", (project["id"],)).fetchone()[0]
    with monkeypatch.context() as patch:
        if break_migration:
            patch.setattr(researchstore, "_SCHEMA", (*researchstore._SCHEMA, "INVALID MIGRATION SQL"))
            with pytest.raises(sqlite3.OperationalError):
                researchstore.list_projects()
        else:
            assert researchstore.get_project(project["id"])["title"] == "Legacy retained"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT document FROM projects WHERE id=?", (project["id"],)).fetchone()[0] == before
        assert connection.execute("PRAGMA user_version").fetchone()[0] == (1 if break_migration else 2)
        assert bool(connection.execute("SELECT name FROM sqlite_master WHERE name='workspace_revisions'").fetchone()) != break_migration
    assert researchstore.get_project(project["id"])["title"] == "Legacy retained"
