# RES-604 implementation log

Repository: `D:\projects\DynamisScience`

Authorized baseline: `eedb7081f68def9654fb0cd7a4fc71b5d8cfd8a2` (`RES-605`)

Private data root: `D:\datasets\DynamisScience` (read-only source during verification)

## G1 — Native scientific workstation

**Implementation status:** The native research journey is implemented and verified on disposable copies. G1 remains open against two measured design targets listed below; work continues through G2–G4.

Implemented:

- PySide6 Widgets `QMainWindow`, project/study/dataset tree, stacked research workspace, docked inspector and five research tabs.
- Direct `DynamisAppService` with no FastAPI/Uvicorn imports, validated external data root, native SQLite/Parquet access, cohort exploration, runs, evidence, lineage, report citation/freezing and HTML export.
- Bounded 500-row Arrow table paging in `QAbstractTableModel`; page reads and study operations run off the GUI thread.
- `pyqtgraph` force-signal viewing with per-plate peak-preserving decimation; CPU-heavy MixedLM, ICC and signal QA run in a hidden isolated Python process.
- Matplotlib QtAgg scientific plots and provenance-bearing PNG/PDF/SVG exports. Figures use stored analysis results and diagnostics; plotting does not recalculate scientific estimates.
- Source license and privacy metadata are read from the admitted snapshot manifest. Synthetic and real-data workspaces retain separate provenance labels.
- Native report versions and SQLite persistence were exercised across a close/reopen cycle.

Verification (Windows 11 x64, Python 3.12.13):

- `uv run pytest tests/test_desktop.py -q` — passed (5 tests), including Mendeley and MoveSmart workflows, exact direct/subprocess result-digest parity, bounded waveform rendering, GUI analysis/evidence/report journey, restart persistence and database integrity.
- `$env:QT_QPA_PLATFORM='offscreen'; uv run pytest -q` — full existing science suite passed. The suite emitted one existing Starlette/httpx deprecation warning.
- `uv run python -m compileall -q dynamis_science/desktop scripts/benchmark_desktop.py tests/test_desktop.py` — passed.
- Fresh-process import check — `fastapi_loaded=False`, `uvicorn_loaded=False`, `qtwebengine_available=False`.
- The benchmark script verified copied Parquet SHA-256 values and used SQLite's online backup API to create a disposable research database. The source root and its research store were not written.
- The pre-existing `data/synthetic/generator_manifest.json` working-tree edit had the same SHA-256 before and after the full test suite.

GUI evidence: [synthetic native research workstation](evidence/g1-native-synthetic.png). The reproducible capture uses `QT_QPA_PLATFORM=windows`, a temporary data root and `STUDY-001` (`DS-SYNTH-001`); no private participant data is shown.

Performance results: [G1 benchmark JSON](evidence/g1-desktop-benchmarks.json). The script ran with `QT_QPA_PLATFORM=offscreen`; cold-start samples use a new process each time, with the OS file cache warm.

| Benchmark | Measured | Design target | Result |
|---|---:|---:|---|
| Cold start to populated catalogue (5 samples) | median 1,297 ms; p95 1,371 ms | median <1,500 ms | Met |
| Idle working set, 5 s after opening Mendeley | 200.22 MB | <250 MB | Met |
| First `force_signals.parquet` page (500 rows) | 31.44 ms; +2.24 MB working set | <80 ms; <25 MB delta | Met |
| MoveSmart waveform to plot update | 52.97 ms | <120 ms | Met |
| Mendeley MixedLM worker runtime | 3,342.6 ms; 4,311.3 ms wall | <2,500 ms | Missed; qualified optimizer sequence preserved |
| Maximum GUI timer gap during MixedLM | 18.09 ms | <16 ms | Missed by 2.09 ms |
| Peak session working set including report export | 227.46 MB | <500 MB | Met |

The two missed performance targets remain tracked; no numerical method, optimizer or tolerance was changed to improve the benchmark.

## G2 — Research authoring and data management

Not started. Project/study CRUD, cohort and plan authoring/versioning, admission/QC/quarantine and complete report composition remain.

## G3 — Performance OS

Not started. Native Today, Plan, Monitor, Test, Research, Report and Athlete 360 workspaces remain.

## G4 — Packaging and web retirement

Not started. Windows `--onedir` / Inno Setup packaging, install/uninstall and offline verification, recovery UI, licensing bundle, parity audit and web-runtime retirement remain.

## Commits

Every implementation commit uses a `RES-604` subject. The native service/UI implementation commit is `0377177` (`RES-604: implement native research workstation`). Evidence and benchmark artifacts are recorded in the following `RES-604` commit and in the Linear issue; the gate remains open while the two measured performance targets are reviewed.
