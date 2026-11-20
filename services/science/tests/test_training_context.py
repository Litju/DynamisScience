"""Executable source admission checks for the native training context workflow."""

import csv
from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from dynamis_science import admission, context_timeline as timeline, training_context as context
from dynamis_science.desktop.main_window import MainWindow
from dynamis_science.desktop.training_context import ContextSourceDialog
from test_reconciliation import setup  # noqa: F401

SOURCE = "CONTEXT-STUDY"
FIELDS = (*context.REQUIRED, *context.OPTIONAL)


def export(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def training(**changes):
    return {"participant": "A01", "record_id": "session-1", "kind": "TRAINING", "status": "OBSERVED",
            "occurred_at": "2026-08-01T18:00:00-03:00", "scheduled_at": "2026-08-01T17:30:00-03:00",
            "duration": "2400", "duration_unit": "s", "rpe": "5.5", "rpe_scale": "CR10", **changes}


def wellness(**changes):
    return {"participant": "A01", "record_id": "wellness-1", "kind": "WELLNESS", "status": "MISSING",
            "scheduled_at": "2026-08-02T09:00:00-03:00", "measure": "sleep_duration", "unit": "h",
            "questionnaire": "Morning check-in", "questionnaire_version": "1", "reason": "No response", **changes}


@pytest.fixture
def workspace(setup):
    service, identity, _, detail = setup
    admission.register_source({
        "id": SOURCE, "name": "Synthetic training log", "publisher": "Test lab",
        "dataset_identity": "Context fixture", "version": "1", "acquisition_method": "Fixture",
        "license_or_agreement": "Internal fixture only", "redistribution_restrictions": "Internal",
        "permitted_uses": ["research"], "privacy_status": "TEST_FIXTURE", "rights_status": "FIXTURE_ONLY",
    })
    return service, identity, detail["active_data_revision_id"]


@pytest.mark.parametrize(("rows", "mappings", "error"), [
    ([training(participant="A07")], {"A07": "A08"}, "Participant mapping conflict"),
    ([training(participant="unknown")], {}, "Participant mapping conflict"),
    ([training(), training()], {}, "unique within the source"),
    ([training(), training(record_id="duplicate")], {}, "Duplicate observation"),
    ([training(duration_unit="m")], {}, "min or s"),
    ([training(rpe_scale="CR20")], {}, "CR10"),
    ([training(occurred_at="2026-08-01T18:00:00")], {}, "explicit UTC offset"),
    ([training(occurred_at="2026-02-30T18:00:00-03:00")], {}, "explicit UTC offset"),
    ([training(occurred_at="2026-08-01T18:00:00-03:70")], {}, "explicit UTC offset"),
    ([training(occurred_at="2026-08-01T18:00:00-00:00")], {}, "explicit UTC offset"),
    ([wellness(value="8")], {}, "explicitly missing"),
    ([wellness(), wellness(participant="A02", record_id="wellness-2", unit="s")], {}, "one explicit measurement unit"),
])
def test_source_rejections(workspace, tmp_path, rows, mappings, error):
    _, identity, revision = workspace
    file = export(tmp_path / "invalid.csv", rows)
    with pytest.raises(ValueError, match=error):
        context.preview(identity, revision, SOURCE, file, context.SourceMapping(participants=mappings))
    assert context.source_history(identity, revision) == []


def test_native_workspace_import_reviews_and_reads_source(qtbot, workspace, tmp_path, monkeypatch):
    service, identity, revision = workspace
    file = export(tmp_path / "session-and-wellness.csv", [
        training(participant="External-01"), wellness(participant="External-01"),
        training(participant="A02", record_id="session-2", rpe=None, rpe_scale=None),
    ])
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(file), ""))
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: errors.append(args[-1]))
    window = MainWindow(service)
    qtbot.addWidget(window)
    window.resize(1366, 820)
    window.show()

    def idle():
        qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)

    idle()
    window._show_study(identity, service.get_study_detail(identity))
    idle()
    window._go_research_stage("Training context")
    idle()
    panel = window.research.training_context
    assert panel.scope.count() == 21

    def review():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, ContextSourceDialog)
        dialog.sources.setCurrentIndex(dialog.sources.findData(SOURCE))
        dialog.participants.setText("External-01=A01")
        dialog.file_button.click()
        dialog.preview_button.click()
        assert dialog.attach_button.isEnabled(), dialog.details.toPlainText()
        assert "220 AU" in dialog.details.toPlainText()
        assert "INCOMPLETE_EXPOSURE" in dialog.details.toPlainText()
        dialog.attach_button.click()

    QTimer.singleShot(0, review)
    panel.add_source.click()
    idle()
    assert errors == []
    assert panel.table.rowCount() == 3
    panel.scope.setCurrentIndex(panel.scope.findData("A01"))
    idle()
    assert panel.table.rowCount() == 2
    assert "220 AU" in panel.table.item(0, 3).text()
    assert "No response" in panel.table.item(1, 3).text()
    assert "Synthetic training log" in panel.table.item(0, 5).text()
    sources, rows = context.observations(identity, revision, ["A02"])
    assert sources[0]["qc"] == {"AFTER_SCHEDULE": 2, "MISSING": 1, "INCOMPLETE_EXPOSURE": 1}
    assert rows[0]["session_load_au"] is None and rows[0]["duration_min"] == 40


def test_context_version_integrity_rights_and_repeat_file(workspace, tmp_path):
    _, identity, revision = workspace
    mapping = context.SourceMapping()
    source = export(tmp_path / "source.csv", [training()])
    preview, _ = context.preview(identity, revision, SOURCE, source, mapping)
    first = context.attach(identity, revision, SOURCE, source, mapping, preview, "Researcher")
    assert context.attach(identity, revision, SOURCE, source, mapping, preview, "Researcher") == first
    view = timeline.build(identity, revision, timeline.TimelineQuery(subject_id="A01"))
    frozen = timeline.freeze(view, "First recorded load")
    updated = export(tmp_path / "source-v2.csv", [training(rpe="6")])
    preview, _ = context.preview(identity, revision, SOURCE, updated, mapping)
    new = context.attach(identity, revision, SOURCE, updated, mapping, preview, "Researcher")
    assert new["version"] == 2 and new["changes"] == {"changed": 1}
    assert timeline.reopen(identity, frozen["id"]) == frozen
    with pytest.raises(RuntimeError, match="changed"):
        timeline.freeze(view, "Stale view")
    active = context.observations(identity, revision, ["A01"])[1][0]
    previous = context.observations(identity, revision, ["A01"], [first["id"]])[1][0]
    assert (active["session_load_au"], previous["session_load_au"]) == (240, 220)
    artefact = admission.get_source_artifact(new["artifact_id"])
    Path(artefact["stored_path"]).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        context.observations(identity, revision, ["A01"])
    assert timeline.reopen(identity, frozen["id"]) == frozen
    registry = admission._artifact_path("admission_sources.json")
    rows = admission.list_sources()
    admission._save_list(registry, [{**row, "permitted_uses": []} if row["id"] == SOURCE else row for row in rows])
    with pytest.raises(ValueError, match="research permission"):
        timeline.reopen(identity, frozen["id"])


def test_context_attachment_rolls_back_parquet_when_catalogue_commit_fails(workspace, tmp_path, monkeypatch):
    from dynamis_science import researchstore as store
    from dynamis_science.data_root import paths

    _, identity, revision = workspace
    file = export(tmp_path / "attachment.csv", [training()])
    mapping = context.SourceMapping()
    preview, _ = context.preview(identity, revision, SOURCE, file, mapping)
    with monkeypatch.context() as patch:
        def fault(*args, **kwargs):
            raise RuntimeError("injected catalogue failure")

        patch.setattr(store, "_audit", fault)
        with pytest.raises(RuntimeError, match="injected catalogue failure"):
            context.attach(identity, revision, SOURCE, file, mapping, preview, "Independent reviewer")
    assert context.source_history(identity, revision) == []
    assert not list((paths()["research"] / "context").glob("*.parquet"))
    assert context.attach(identity, revision, SOURCE, file, mapping, preview, "Independent reviewer")["version"] == 1
