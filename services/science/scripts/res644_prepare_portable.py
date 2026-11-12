"""Prepare synthetic files and a saved import profile; no datasets or workspace are pre-created."""
import json
import os
import sys
from pathlib import Path

work = Path(sys.argv[1]).resolve()
work.mkdir(parents=True, exist_ok=False)
os.environ["DYNAMISSCIENCE_DATA_ROOT"] = str(work / "private")
from dynamis_science import admission, importer
from dynamis_science.desktop.services import DynamisAppService
service = DynamisAppService()
service.ensure_initialized()
fields = {"source_name": "RES-644 portable synthetic lab", "publisher": "DynamisScience qualification",
          "dataset_identity": "RES-644-portable", "license_or_agreement": "Internal fixture only",
          "redistribution_restrictions": "Synthetic fixture only", "privacy_status": "TEST_FIXTURE",
          "manufacturer": "Simulated", "model": "Fixture", "serial_number": "SYNTH-644",
          "protocol_name": "Fixture CMJ", "protocol_version": "1.0", "sampling_hz": "1000"}
for number in (1, 2):
    (work / f"batch{number}.csv").write_text(
        "Athlete,Trial,Jump Height (cm),Body Mass (kg),Peak Force (N),week,session_id,sampling_hz\n" +
        f"A1,T{number}a,{39+number},80,1800,{number},S{number},1000\nA2,T{number}b,{37+number},75,1700,{number},S{number},1000\n")
plan = importer.probe_file(work / "batch1.csv")
context = importer.build_context(fields)
importer.save_preset("RES-644 synthetic CMJ profile", plan, context)
assert not admission.list_admitted_snapshots() and not service.list_projects()
assert not [study for study in service.list_all_studies() if study.get("workspace")]
(work / "preparation.json").write_text(json.dumps({"data_root": str(service.root), "datasets": 0, "workspaces": 0, "profile_only": True}, indent=2))
print(work)
