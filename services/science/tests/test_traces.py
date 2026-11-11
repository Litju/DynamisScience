from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from dynamis_science import admission, importer, traces
from dynamis_science.desktop.services import DynamisAppService

from test_importer import FIXTURE, _file

CONST = {"session_id": "S1", "sampling_hz": 1000}


@pytest.fixture
def service(monkeypatch, tmp_path):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    app = DynamisAppService()
    app.ensure_initialized()
    return app


def _csv(tmp_path, name, rows, header="Athlete,Trial,Time (s),Force (N)"):
    return _file(tmp_path, name, header + "\n" + "\n".join(rows) + "\n")


def _two_traces(n=1000):
    return [f"{s},{t},{i / 1000:.3f},{700 + i % 7}" for s, t in (("A1", "T1"), ("A2", "T2")) for i in range(n)]


def _ready(path, **extra):
    return importer.edit_mapping(importer.probe_file(path), {}, {**extra})


def _stage(path, fields=FIXTURE, **constants):
    return importer.stage(_ready(path, **constants), importer.build_context(fields))


def test_repeated_trial_ids_across_samples_are_valid(service, tmp_path):
    path = _csv(tmp_path, "t.csv", _two_traces())
    plan = importer.probe_file(path)
    assert plan["mapping"]["family"] == traces.FAMILY and plan["rows"] == 2000
    staged = _stage(path, **CONST)
    assert staged["quality"]["status"] == "ADMITTED_WITH_WARNINGS" and staged["eligible"], staged["quality"]
    assert any("orientation" in w for w in staged["quality"]["warnings"])  # never silently assumed
    record = importer.admit(staged)
    assert record["admission_class"] == "SYNTHETIC_ONLY"
    snap = admission.get_admitted_snapshot(record["dataset_snapshot_id"])
    assert snap["row_counts"] == {"force_signals": 2000, "trace_index": 2}
    index = pl.read_parquet(Path(snap["path"]) / "trace_index.parquet")
    assert index["n_samples"].to_list() == [1000, 1000] and index["sampling_hz_declared"].to_list() == [1000.0] * 2
    assert set(snap["checksums"]) == {"force_signals.parquet", "trace_index.parquet"}


def test_workbench_lists_traces_and_plots_waveform(service, tmp_path):
    record = importer.admit(_stage(_csv(tmp_path, "t.csv", _two_traces()), **CONST))
    sid = record["dataset_snapshot_id"]
    assert sid in {d["id"] for d in service.list_datasets()}
    trials = service.list_signal_trials(sid)
    assert sorted(t["trial_id"] for t in trials) == ["T1", "T2"]
    wave = service.get_signal_waveform(sid, "T1")
    assert wave["source_rows"] == 1000 and wave["series"][0]["value_column"] == "force_z_n"
    assert not service.list_signal_trials(sid, subject_id="nobody")


def test_single_trace_vendor_shaped_file_needs_identity_then_two_channels(service, tmp_path):
    body = "\n".join(f"{i / 1000:.3f},{400 + i % 5},{300 + i % 3}" for i in range(500))
    path = _file(tmp_path, "one.csv", "Time (s),Left Force (N),Right Force (N)\n" + body + "\n")
    plan = importer.probe_file(path)
    assert plan["state"] == "REVIEW" and any("subject_id" in n for n in plan["needs"])  # never invented
    staged = _stage(path, subject_id="A9", trial_id="T-single", **CONST)
    assert staged["eligible"]
    sid = importer.admit(staged)["dataset_snapshot_id"]
    labels = [s["label"] for s in service.get_signal_waveform(sid, "T-single")["series"]]
    assert labels == ["left", "right"]


def test_sample_index_with_declared_rate_derives_time(service, tmp_path):
    path = _csv(tmp_path, "i.csv", [f"A1,T1,{i},{500 + i % 3}" for i in range(200)], header="Athlete,Trial,Sample,Force (N)")
    assert any("time" in n for n in importer.edit_mapping(importer.probe_file(path), {}, {"session_id": "S"})["needs"])
    staged = _stage(path, **CONST)
    sid = importer.admit(staged)["dataset_snapshot_id"]
    t = pl.read_parquet(Path(admission.get_admitted_snapshot(sid)["path"]) / "force_signals.parquet")["time_s"]
    assert t[1] == pytest.approx(0.001) and staged["receipt"]["admission_metadata"]["time_base"] == "sample_index/sampling_hz"


def test_estimated_sampling_is_labelled(service, tmp_path):
    staged = _stage(_csv(tmp_path, "e.csv", _two_traces(300)), session_id="S1")
    md = staged["receipt"]["admission_metadata"]
    assert md["sampling_source"] == "estimated_from_timestamps" and md["sampling_hz"] == pytest.approx(1000.0)
    assert any("estimated" in w for w in staged["quality"]["warnings"])


@pytest.mark.parametrize("rows,expected,why", [
    ([f"A1,T1,{i // 2 / 1000},700" for i in range(100)], "REJECTED", "duplicate or non-increasing"),
    ([f"{'A1' if i < 50 else 'A2'},T1,{i / 1000},700" for i in range(100)], "REJECTED", "several subjects"),
    ([f"A1,T1,{i / 500},700" for i in range(100)], "REJECTED", "imply"),
    ([f"A1,T1,{i / 1000},{50000 if i == 5 else 700}" for i in range(100)], "QUARANTINED", "implausible"),
    ([f"A1,T1,{i / 1000},{'' if i == 5 else 700}" for i in range(100)], "ADMITTED_WITH_WARNINGS", "missing"),
])
def test_trace_qc_is_conservative(service, tmp_path, rows, expected, why):
    staged = _stage(_csv(tmp_path, "q.csv", rows), **CONST)
    assert staged["quality"]["status"] == expected
    assert any(why in m for m in staged["quality"]["errors"] + staged["quality"]["warnings"])
    if expected != "ADMITTED_WITH_WARNINGS":
        assert not staged["eligible"]
        assert importer.quarantine(staged)["admission_record"]["dataset_snapshot_id"] is None
        assert not admission.list_admitted_snapshots()


def test_non_numeric_samples_are_blocked(service, tmp_path):
    rows = [f"A1,T1,{i / 1000},700" for i in range(50)] + ["A1,T1,0.9,oops"]
    with pytest.raises(importer.ImportBlocked, match="could not be normalized"):
        _stage(_csv(tmp_path, "n.csv", rows), **CONST)


def test_real_trace_data_never_inherits_fixture_leniency(service, tmp_path):
    real = {**FIXTURE, "privacy_status": "DEIDENTIFIED", "source_name": "Real lab"}
    path = _csv(tmp_path, "r.csv", _two_traces(200))
    assert not _stage(path, real, **CONST)["eligible"]  # rights unverified
    staged = importer.stage(_ready(path, **CONST), importer.build_context(real), rights_reviewed_by="tester")
    assert staged["quality"]["status"] == "QUARANTINED" and not staged["eligible"]  # calibration unknown
    ok = importer.stage(_ready(path, **CONST), importer.build_context({**real, "calibration_status": "CALIBRATED"}),
                        rights_reviewed_by="tester")
    assert ok["eligible"] and not ok["synthetic_only"]


def test_reimport_is_idempotent_and_snapshot_immutable(service, tmp_path):
    path = _csv(tmp_path, "r.csv", _two_traces(200))
    first = importer.admit(_stage(path, **CONST))
    again = importer.admit(_stage(path, **CONST))
    assert again["id"] == first["id"] and len(admission.list_admitted_snapshots()) == 1
    snap = Path(admission.get_admitted_snapshot(first["dataset_snapshot_id"])["path"])
    before = (snap / "force_signals.parquet").read_bytes()
    importer.admit(_stage(path, **CONST))
    assert (snap / "force_signals.parquet").read_bytes() == before


def test_batch_boundaries_do_not_change_qc(service, tmp_path, monkeypatch):
    staged = _stage(_csv(tmp_path, "b.csv", _two_traces(1500)), **CONST)
    full = staged["quality"]["counts"]
    monkeypatch.setattr(traces, "BATCH_ROWS", 333)
    small = traces.scan(Path(staged["artifact"]["stored_path"]), ["force_z_n"])
    assert full == {"samples": 3000, "traces": 2, "subjects": 2, "channels": 1}
    assert small["rows"] == 3000 and {k: v["n"] for k, v in small["traces"].items()} == {("A1", "S1", "T1"): 1500, ("A2", "S1", "T2"): 1500}


def test_interleaved_rows_merge_by_key(service, tmp_path, monkeypatch):
    rows = _two_traces(300)
    interleaved = [r for pair in zip(rows[:300], rows[300:]) for r in pair]
    monkeypatch.setattr(traces, "BATCH_ROWS", 50)
    staged = _stage(_csv(tmp_path, "x.csv", interleaved), **CONST)
    assert staged["quality"]["counts"]["traces"] == 2 and staged["eligible"]


def test_probe_enforces_resource_limits(tmp_path, monkeypatch):
    path = _csv(tmp_path, "l.csv", _two_traces(100))
    monkeypatch.setattr(importer, "MAX_TRACE_BYTES", 100)
    assert "import limit" in importer.probe_file(path)["reason"]
    monkeypatch.setattr(importer, "MAX_TRACE_BYTES", 1 << 30)
    monkeypatch.setattr(traces, "MAX_ROWS", 10)
    assert "More than" in importer.probe_file(path)["reason"]
    summary = _file(tmp_path, "s.csv", "Athlete,Trial,Jump Height (cm)\nA,1,40\n")
    monkeypatch.setattr(importer, "MAX_FILE_BYTES", 5)
    assert "Trial-level tables above" in importer.probe_file(summary)["reason"]
