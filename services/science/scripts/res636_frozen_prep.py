"""Prepare a disposable root and input files for the frozen-application walkthrough (RES-636).

Usage: python scripts/res636_frozen_prep.py <work-dir>
Creates <work-dir>/private (data root with two saved presets) and <work-dir>/inputs (CSV files).
The frozen executable is then driven by scripts/res636_frozen_drive.ps1 against exactly this root.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

work = Path(sys.argv[1]).resolve()
os.environ["DYNAMISSCIENCE_DATA_ROOT"] = str(work / "private")
os.environ.pop("DYNAMISSCIENCE_TEST_SESSION", None)

from dynamis_science import importer  # noqa: E402

(work / "inputs").mkdir(parents=True, exist_ok=True)
HEADER = "Athlete,Trial,Jump Height (m),Body Mass (g),Peak Force (N)\n"
(work / "inputs" / "cmj_valid.csv").write_text(HEADER + "A1,TR-1,0.401,80000,1189\nA2,T2,0.385,75000,1700\nA3,T3,0.372,82000,1900\n", encoding="utf-8")
(work / "inputs" / "cmj_invalid.csv").write_text(HEADER + "B1,T1,4.0,80000,1800\nB2,T1,0.385,75000,1700\n", encoding="utf-8")
rows = "\n".join(f"{s},{t},{i / 1000:.3f},{700 + (i * 7) % 90 + (400 if 300 < i < 500 else 0)}"
                for s, t in (("A1", "TR-1"), ("A2", "TR-2")) for i in range(1000))
(work / "inputs" / "trace.csv").write_text("Athlete,Trial,Time (s),Force (N)\n" + rows + "\n", encoding="utf-8")

FIELDS = {"source_name": "Frozen walkthrough lab", "publisher": "DynamisScience walkthrough", "dataset_identity": "res636-frozen",
          "license_or_agreement": "Internal fixture only", "redistribution_restrictions": "Fixture only; not real measurements",
          "privacy_status": "TEST_FIXTURE", "manufacturer": "Fixture", "model": "FP-1", "serial_number": "FROZEN-1",
          "protocol_name": "Fixture protocol", "protocol_version": "1.0"}
for name, file in (("Frozen CMJ export", "cmj_valid.csv"), ("Frozen force-time export", "trace.csv")):
    plan = importer.edit_mapping(importer.probe_file(work / "inputs" / file), {}, {"session_id": "S1", "sampling_hz": 1000})
    importer.save_preset(name, plan, importer.build_context(FIELDS))
print(f"prepared {work}")
