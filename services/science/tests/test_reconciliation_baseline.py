"""Replay the manual preparation route against the exact pre-RES-722 implementation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from test_importer import FIXTURE
from test_reconciliation import FIELDS, FOLLOWUP_FIELDS, baseline_rows, followup_rows, write_export

BEFORE = "f8a962639c683a788ca17ca640343d36dc530eec"

REPLAY = r"""
import csv
import json
from pathlib import Path
import sys

from dynamis_science import importer, researchstore as store
from dynamis_science.desktop.services import DynamisAppService

work = Path(sys.argv[1])
context = importer.build_context(json.loads(sys.argv[2]))

def stage(name, context=context):
    return importer.stage(importer.probe_file(work / name), context)

def admit(staged):
    return importer.admit(staged)["dataset_snapshot_id"]

def read(name):
    with (work / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))

def write(name, data):
    with (work / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)

def append(snapshot, base):
    return store.attach_workspace_data(identity, snapshot, append=True, confirm_participant_ids=True,
                                       base_revision=base)

def blocked(snapshot, base):
    try:
        append(snapshot, base)
    except store.ResearchValidation as error:
        return str(error)
    raise AssertionError("The old append should refuse the overlap or protocol mismatch.")

service = DynamisAppService()
identity = service.create_workspace("Historical RES-722 comparison")["study"]["id"]
baseline = admit(stage("baseline.csv"))
first = store.attach_workspace_data(identity, baseline)["active_data_revision_id"]
raw_duplicate = stage("copied-baseline.csv")
assert raw_duplicate["duplicate_of"]
unreviewed = admit(stage("followup.csv"))
unreviewed_rows = store.read_snapshot_table(unreviewed, "cmj_trials")
assert unreviewed_rows.filter(unreviewed_rows["trial_id"] == "F07").select("subject_id", "jump_height_cm").row(0) == ("A07-renamed", 35.5)
overlap = blocked(unreviewed, first)
assert "Overlapping trial_id" in overlap
other_context = {**context, "protocol": {**context["protocol"], "name": "Alternate fixture protocol"}}
unsafe = admit(stage("protocol-change.csv", other_context))
drift = blocked(unsafe, first)
assert "protocol_id" in drift

# Perform the manual off-application edits on the same exports used by the native review.
original, incoming = read("baseline.csv"), read("followup.csv")
correction = [row for row in incoming if row["Trial"] in {baseline["Trial"] for baseline in original}]
assert len(correction) == 1 and correction[0]["Trial"] == "B01"
old = next(row for row in original if row["Trial"] == "B01")
assert (old["Athlete"], old["Session"], old["week"]) == (correction[0]["Player"], "Baseline", correction[0]["week"])
old["Jump Height (cm)"] = str(float(correction[0]["Jump Height (mm)"]) / 10)
write("manually-corrected-baseline.csv", original)
eligible = [row for row in incoming if row not in correction]
for row in eligible:
    if row["Player"] == "A07-renamed":
        row["Player"] = "A07"
    assert row["Test Session"] == "Week 12 export"
    row["Test Session"] = "Follow-up"
write("manually-corrected-followup.csv", eligible)

replacement = admit(stage("manually-corrected-baseline.csv"))
separate = store.attach_workspace_data(identity, replacement, base_revision=first)["active_data_revision_id"]
current = append(admit(stage("manually-corrected-followup.csv")), separate)
active = current["active_data_revision_id"]
result = service.execute_analysis_run(identity, {"data_revision_id": active, "method_id": "METH-U-DESC",
    "outcome_metric_id": "MET-CMJ-HEIGHT", "parameters": {}})["result"]
points = {str(row["week"]): row["mean"] for row in result["points"]}
print(json.dumps({"duplicate_detected_by_original_importer": bool(raw_duplicate["duplicate_of"]),
    "original_importer_normalized_mm": 35.5,
    "unreviewed_athlete": "A07-renamed", "overlap_error": overlap, "protocol_error": drift,
    "outside_app_csv_outputs": 2, "workspace_revisions": len(store.data_revisions(identity)),
    "subjects": result["n_subjects"], "observations": result["n_observations"], "means_cm": points}))
"""


def test_manual_baseline_against_pinned_git_source(tmp_path, capsys):
    repo = Path(__file__).resolve().parents[3]
    archive = tmp_path / "legacy.zip"
    subprocess.run(["git", "-C", str(repo), "archive", "--format=zip", "-o", str(archive),
                    BEFORE, "services/science/dynamis_science"], check=True, timeout=30)
    checkout = tmp_path / "legacy"
    with zipfile.ZipFile(archive) as snapshot:
        snapshot.extractall(checkout)
    inputs = tmp_path / "exports"
    inputs.mkdir()
    baseline = write_export(inputs / "baseline.csv", baseline_rows(), FIELDS)
    (inputs / "copied-baseline.csv").write_bytes(baseline.read_bytes())
    rows = followup_rows()
    rows.append(["A01", "Baseline renamed", "B01", 1, 1000, 310, 73, 1601, "v2"])
    write_export(inputs / "followup.csv", rows, FOLLOWUP_FIELDS)
    write_export(inputs / "protocol-change.csv", [row + ["OTHER-PROTOCOL"] for row in followup_rows()],
                 FOLLOWUP_FIELDS + ["Protocol"])
    env = {**os.environ, "DYNAMISSCIENCE_DATA_ROOT": str(tmp_path / "legacy-data"),
           "PYTHONPATH": str(checkout / "services" / "science")}
    execution = subprocess.run([sys.executable, "-c", REPLAY, str(inputs), json.dumps(FIXTURE)],
                               cwd=checkout, env=env, text=True, capture_output=True, timeout=60)
    assert execution.returncode == 0, execution.stderr
    receipt = json.loads(execution.stdout)
    assert receipt["subjects"] == 20 and receipt["observations"] == 40
    assert receipt["workspace_revisions"] == 3
    assert receipt["means_cm"] == pytest.approx({"1": 35.275, "12": 37.25})
    with capsys.disabled():
        print(f"RES-722 historical {BEFORE}: {json.dumps(receipt, sort_keys=True)}")
