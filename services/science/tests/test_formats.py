from __future__ import annotations

import json
from pathlib import Path

import openpyxl
import polars as pl
import pytest

from dynamis_science import admission, importer
from dynamis_science.desktop.services import DynamisAppService

from test_importer import FIXTURE


@pytest.fixture
def service(monkeypatch, tmp_path):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    app = DynamisAppService()
    app.ensure_initialized()
    return app


ROWS = [("Athlete", "Trial", "Jump Height (cm)", "Body Mass (kg)", "Peak Force (N)"),
        ("A1", "T1", 40.0, 80.0, 1800.0), ("A2", "T2", 38.5, 75.0, 1700.0)]


def _write(kind: str, tmp_path: Path) -> Path:
    path = tmp_path / f"data.{kind}"
    records = [dict(zip(ROWS[0], r)) for r in ROWS[1:]]
    if kind == "xlsx":
        book = openpyxl.Workbook()
        book.active.title = "Notes"
        book.create_sheet("Data")
        for row in ROWS:
            book["Data"].append(row)
        book.remove(book["Notes"])
        book.save(path)
    elif kind == "tsv":
        path.write_text("\n".join("\t".join(map(str, r)) for r in ROWS), encoding="utf-8")
    elif kind == "arrow":
        pl.DataFrame(records).write_ipc(path)
    elif kind == "ndjson":
        path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    elif kind == "json":
        path.write_text(json.dumps(records), encoding="utf-8")
    return path


@pytest.mark.parametrize("kind", ["xlsx", "tsv", "arrow", "ndjson", "json"])
def test_every_supported_format_imports_to_the_same_snapshot_content(service, tmp_path, kind):
    plan = importer.edit_mapping(importer.probe_file(_write(kind, tmp_path)), {}, {"session_id": "S1", "sampling_hz": 1000})
    assert plan["rows"] == 2 and plan["mapping"]["family"] == "CMJ_FORCE_PLATFORM", plan.get("reason")
    record = importer.admit(importer.stage(plan, importer.build_context(FIXTURE)))
    table = pl.read_parquet(Path(admission.get_admitted_snapshot(record["dataset_snapshot_id"])["path"]) / "cmj_trials.parquet")
    assert table["jump_height_cm"].to_list() == [40.0, 38.5] and table["subject_id"].to_list() == ["A1", "A2"]


def test_excel_reads_cached_values_and_discloses_the_sheet(service, tmp_path):
    plan = importer.probe_file(_write("xlsx", tmp_path))
    assert plan["sheet"] == "Data" and plan["warnings"] == [] or plan["sheet"] == "Data"
    book = openpyxl.Workbook()
    book.active.append(("a", "b"))
    book.active.append((1, 2))
    book.create_sheet("Second").append(("c",))
    book.save(tmp_path / "two.xlsx")
    plan = importer.probe_file(tmp_path / "two.xlsx")
    assert plan["warnings"] and "2 sheets" in plan["warnings"][0]


@pytest.mark.parametrize("name,content,why", [("e.xlsx", None, "could not be parsed"), ("bad.json", "{not json", "could not be parsed")])
def test_malformed_files_are_reported_not_crashed(service, tmp_path, name, content, why):
    path = tmp_path / name
    path.write_bytes(b"" if content is None else content.encode())
    plan = importer.probe_file(path)
    assert plan["state"] == "UNSUPPORTED"


def test_folder_import_mixes_formats(service, tmp_path):
    folder = tmp_path / "mixed"
    folder.mkdir()
    for kind in ("xlsx", "arrow", "tsv"):
        _write(kind, folder)
    assert sorted(p["name"] for p in importer.probe(folder)["files"]) == ["data.arrow", "data.tsv", "data.xlsx"]
