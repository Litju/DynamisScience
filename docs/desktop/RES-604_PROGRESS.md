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

**Implementation status:** Authoring and admission workflows are implemented and verified. The shared G1 performance targets remain open as recorded above.

Implemented:

- Native project create/edit/archive/restore; study and monitoring-program create/edit, version history and state transitions.
- Cohort include/exclude IDs, JSON rules, minimum-observation/activity filters, resolution table, draft edits, freeze, fork and history.
- Analysis plan method/metric/cohort selection, JSON parameters, estimand/design fields, optimistic update, freeze, fork and history.
- Native local-source admission uses streamed file copies, source-rights review/verification, instrument/protocol manifests, QC results, admitted snapshots and rejected/quarantined history.
- Admitted CMJ snapshots are available to the research catalogue and can be used to create studies without copying data into the real snapshot store. Only registered metrics and methods are offered.
- Report narrative fields, evidence citation removal, optimistic versioning, freeze history and frozen HTML export.

Verification:

- `uv run pytest tests/test_research_authoring.py -q` — passed (2 backend authoring/admission tests).
- `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_desktop.py -q` — passed, including native project/study/monitoring dialogs, cohort and plan freeze/fork, report composition, source QC/admission and quarantine viewing.
- `QT_QPA_PLATFORM=offscreen uv run pytest -q` — full science suite passed with the existing Starlette/httpx deprecation warning.
- Private snapshots and the research database were copied to disposable roots for integration tests; the private source root and pre-existing manifest edit remain unchanged.

GUI evidence: [native study authoring dialog using the synthetic fixture](evidence/g2-study-authoring.png).

G2 commits: `1c4d8c6` (`RES-604: integrate local admission and research authoring`) and `fd29072` (`RES-604: author research and admissions in Qt`).

## G3 — Performance OS

**Implementation status:** The operational workflows and the approved Direction F visual system are implemented in native Qt Widgets. Performance OS records stay under the configured private data root and remain isolated from admitted scientific records. G3 verification has passed; the two G1 scientific-worker timing targets remain open.

Implemented:

- Six-section Direction F shell: branded season/search header; Daily and Evidence rail; squad-availability footer; right-side daily context; five-cell squad pulse; attention queue; weekly load, CMJ force-time, research and next-action modules.
- Native Athlete 360 dock with readiness, sleep, load ratio, descriptive baseline change and practitioner notes. The full Athlete 360 page remains available from the dock.
- Native Plan microcycle editor and publish action; Monitor load/wellness/session-log view with a match-tracking and pose inspector; Test trial table and append-only reliability assessment; Research evidence/unit/metric link; audience-specific Reports with freeze and HTML export.
- The approved `docs/design/res588-ux/prototypes/f/` design and `apps/web/app/performance.css` tokens are translated to `QPalette`, scoped QSS, Qt layouts, `QTableView`, `QDockWidget` and `pyqtgraph`; no browser rendering was introduced.
- Performance OS calls the existing `performance.py` functions through `DynamisAppService`. The screens use actual fixture and persisted operational values, retain honest unavailable states, and show the `DS-SYNTH-001` provenance badge.

Verification (Windows 11 x64, Python 3.12.13):

- `$env:QT_QPA_PLATFORM='offscreen'; uv run pytest tests/test_desktop.py -q` — passed (11 tests), including navigation through all eight native pages, workflow buttons, Athlete 360 dock, reports, persistence and bounded match/pose rendering.
- `$env:QT_QPA_PLATFORM='offscreen'; uv run pytest -q` — full science suite passed with one existing Starlette/httpx deprecation warning.
- `uv run python -m compileall -q dynamis_science/desktop tests/test_desktop.py scripts/benchmark_performance_os.py` — passed.
- `uv run python scripts/benchmark_performance_os.py --output ../../docs/desktop/evidence/g3-performance-benchmarks.json --evidence-dir ../../docs/desktop/evidence` — passed on Windows using a disposable data root and `DS-SYNTH-001` only.
- The pre-existing `data/synthetic/generator_manifest.json` edit remained byte-identical through the full science suite: SHA-256 `835398DA594421BC9F04647992B0E9CEFD5DC844FD931D1964896B2E164A2587` before and after.

GUI evidence: [Squad Command](evidence/g3-performance-today.png), [Athlete 360 dock](evidence/g3-performance-athlete.png), and [Match & Pose](evidence/g3-performance-match.png). All screenshots use the synthetic fixture and a temporary operational store.

Performance measurements are in [G3 benchmark JSON](evidence/g3-performance-benchmarks.json). On the measured Windows 11 workstation, central page loads ranged from 26 ms to 1,449 ms; the Athlete 360 dock opened in 189 ms; resident working set was 389 MB and peak 392 MB. The largest observed GUI timer gap was 60 ms while opening Match & Pose. G3 has no separate timer-gap target; this measurement remains visible for later optimization. No scientific calculation was moved into presentation code.

**G3 implementation commits:** `f27953d` (`RES-604: add direct Performance OS service operations`) and `df59eac` (`RES-604: port Performance OS design into Qt workspaces`). The G3 evidence commit is recorded below after it is created.

## G4 — Packaging and web retirement

Not started. Windows `--onedir` / Inno Setup packaging, install/uninstall and offline verification, recovery UI, licensing bundle, parity audit and web-runtime retirement remain.

## Commits

Every implementation commit uses a `RES-604` subject. G1 base: `0377177` (`RES-604: implement native research workstation`); G1 evidence: `a02a108` (`RES-604: record native benchmark and G1 evidence`). G2 service: `1c4d8c6`; G2 UI: `fd29072`; G2 evidence: `92ca8e8`. G3 service: `f27953d`; G3 native visual/workflow implementation: `df59eac`. G3 screenshot and benchmark evidence is recorded in the next commit. The two G1 performance-target misses remain visible and unchanged; G4 still includes installation, recovery, offline and web-retirement verification.
