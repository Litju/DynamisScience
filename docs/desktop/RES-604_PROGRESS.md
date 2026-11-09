# RES-604 implementation log

Repository: `D:\projects\DynamisScience`

Authorized baseline: `eedb7081f68def9654fb0cd7a4fc71b5d8cfd8a2` (`RES-605`)

Private data root: `D:\datasets\DynamisScience` (read-only source during verification)

## G1 — Native scientific workstation

**Implementation status:** The native research journey is implemented and verified on disposable copies. One measured G1 timing target remains above its design threshold; the deviation is recorded below without changing qualified numerical methods.

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
| Cold start to populated catalogue (5 samples) | median 1,558.224 ms; p95 3,106.507 ms (first sample 3,490.364 ms) | median <1,500 ms | Missed by 58 ms; p95 reflects one cold outlier |
| Idle working set, 5 s after opening Mendeley | 224.43 MB | <250 MB | Met |
| First `force_signals.parquet` page (500 rows) | 29.370 ms; +2.55 MB working set | <80 ms; <25 MB delta | Met |
| MoveSmart waveform to plot update | 48.994 ms | <120 ms | Met |
| Mendeley MixedLM worker runtime | 2,637.623 ms; 3,730.474 ms wall | <2,500 ms | Missed by 138 ms; qualified optimizer sequence preserved |
| Maximum GUI timer gap during MixedLM | 29.207 ms | <16 ms | Missed; analysis completed, evidence promotion and report export remained responsive |
| Peak session working set including report export | 251.43 MB | <500 MB | Met |

The frozen-candidate BENCH-01..06 protocol ran once at source commit `39315b41974fa7a6b9e535467efb7371bda9c89b` against checksum-verified snapshots and an SQLite backup in a disposable root, using the Windows Qt platform default. The real-data analysis ran in the existing isolated Python subprocess; the benchmark records worker and total wall time, but does not collect per-process CPU utilization. The application remained responsive and completed analysis, evidence promotion and report export. Cold-start median, MixedLM duration and the maximum GUI timer gap are recorded as explicit target deviations; no equation, optimizer sequence or tolerance changed.

## G2 — Research authoring and data management

**Implementation status:** Authoring and admission workflows are implemented and verified. The remaining G1 MixedLM duration deviation is recorded above.

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

**Implementation status:** The operational workflows and the approved Direction F visual system are implemented in native Qt Widgets. Performance OS records stay under the configured private data root and remain isolated from admitted scientific records. G3 verification has passed; the remaining G1 MixedLM duration deviation is recorded above.

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

**G3 commits:** `f27953d` (`RES-604: add direct Performance OS service operations`), `df59eac` (`RES-604: port Performance OS design into Qt workspaces`), and `7a25fdb` (`RES-604: capture Direction F G3 verification evidence`).

## G4 — Packaging and web retirement

**Implementation status:** Complete. The native parity review passed, the legacy web and HTTP application code has been retired, and the final exact-source Windows installer passed its installed-app, analysis-worker, recovery, offline and uninstall checks. G1's remaining performance target misses remain visible under G1.

Completed in G4 so far:

- Split the Performance OS domain from its HTTP routes, then retired both `performance_http.py` and `api.py` after native parity verification. Qt calls `DynamisAppService` and existing Python scientific/domain modules directly.
- Removed `apps/web`, TypeScript contract/UI packages, pnpm scripts and lockfiles, web-only Playwright automation, FastAPI/Uvicorn, multipart upload, httpx and Playwright dependencies.
- The fresh-process regression check confirms the native import path loads no FastAPI, Uvicorn or QtWebEngine; a post-retirement environment check also confirms FastAPI, Uvicorn, httpx and Playwright are not installed.
- PyInstaller 6.22.3 remains a build-only dependency. Inno Setup 6.7.3 builds the per-user installer. `uv lock --check` and `uv sync --locked` passed after retiring the web dependency graph.
- Added a Windows-first PyInstaller `--onedir` spec and per-user Inno Setup installer. The build stages a disposable `DS-SYNTH-001` fixture under an ignored, unique build directory; no private Mendeley/MoveSmart data enters the bundle.
- Fixed the first frozen-launch defects found by real installed runs: remove host Poppler ICU DLL contamination, explicitly collect pyqtgraph's dynamic `PySide6.QtOpenGL` and `QtOpenGLWidgets` imports, and resolve the private-root safety boundary from the installed executable directory when frozen.
- Added native SQLite integrity inspection, online backup verification and isolated restore rehearsal, plus a native independent real-data qualification action running through the isolated worker and an optional external R/lme4 reference. Application exceptions are logged to a rotating file under the configured private root; scientific execution uses the packaged `--worker` file-IPC entry point in a separate process.
- The final frozen build explicitly collects Matplotlib QtAgg, Agg, PDF and SVG backends, and bundles the `qualification_real.py` module and `real_mixedlm.R` reference script.
- Bundled third-party license notices and the LGPL-3.0 text, with an in-app Help menu viewer. The Qt redistribution notices remain included in the installer.
- Added a read-only native scientific library for metric, protocol, method and model definitions. Prototype and unavailable entries display their stored status and limitations; the dialog does not execute unsupported methods.
- Added a native versioned investigation editor with typed blocks, JSON state editing, add/remove/reorder, dependency-order validation, optimistic saves and fork lineage. Added a side-by-side HTML diff for frozen report versions and a clickable Qt provenance DAG with stored-node details.
- The admission, Performance OS and scientific regression tests now call the direct Python facade/domain. The legacy HTTP client tests have been replaced by the native workflows and direct storage/science assertions.

Windows packaging verification (Windows 11 x64, Python 3.12.13, PyInstaller 6.22.3, Inno Setup 6.7.3):

- The final exact-source build used commit `5447b5466fdd1b81b20a055275e98374a24cea7c`. Its worktree status was only the preserved line-ending edit in `data/synthetic/generator_manifest.json`, with source diff SHA-256 `D0691F70663717FC86A4D9AB51AD62650903F0F3D19AB21457FABEB593DDBF4B`. Bundle size: `582,741,889` bytes; installer size: `141,528,142` bytes; installer SHA-256: `17C04C46F882690EDF49FA799DCD958C89938EEE0959CF9621E7AB0166889B2F`. The build collected notices for 35 runtime distributions and the PyInstaller bootloader license.
- The installed package checks passed on Windows 11 x64: unpacked, installed catalogue, installed Performance OS Today, reopened catalogue, and post-restore catalogue startup took `3,695 ms`, `1,608 ms`, `4,615 ms`, `1,571 ms`, and `1,082 ms`. Installed working sets were `108.69 MB` for the catalogue, `232.86 MB` for Today, `128.37 MB` after study reopen, and `125.93 MB` after restore. The unpacked-launch `5.51 MB` sample is implausibly low and is excluded from memory conclusions. All runs observed zero listening TCP ports.
- The installed scientific worker matched direct result digests for synthetic `METH-U-DESC`, Mendeley `METH-REAL-TREND`, and MoveSmart `METH-REAL-RELIABILITY` and `METH-REAL-SIGNAL-QA`. Independent Mendeley MixedLM, MoveSmart ICC and signal qualifications all returned `QUALIFIED`; the synthetic-only qualification state returned `NO_REAL_SNAPSHOTS`. The installed Matplotlib worker produced provenance-bearing PNG, PDF and SVG exports. The PyInstaller archive contains the QtAgg, Agg, PDF and SVG backends, worker, qualification module and SQLite recovery module; installed checks confirmed the QtWidgets/QtOpenGL modules, pyqtgraph and license resources.
- SQLite integrity, online backup, isolated restore, reopen and uninstall preservation passed. The private root's five SQLite files retained the same aggregate fingerprint before and after qualification (`FEF535256162EC5297E1C091B54299687A80EDD1E525C4EB9400C1743CBCAC41`). The disposable installer test root, including copied real research data, was removed.
- `uv run pytest -q` passed all 93 tests at application-source commit `39315b41974fa7a6b9e535467efb7371bda9c89b`, with R 4.6.2 and lme4 2.1.0. The later commits before packaging changed only benchmark/progress documentation and the build script's source-stamp capture; application, test and packaging-spec source remained the same. The updated test and package evidence is in [G4 packaging benchmarks](evidence/g4-packaging-benchmarks.json) and the [final release receipt](evidence/final-release-receipt.json).
- The installer, app executable and host `Rscript.exe` are unsigned; none has a Mark-of-the-Web zone stream. The bundled `real_mixedlm.R` is plain script content and also has no zone stream. The user reported Windows blocked the R qualification invocation and selected Allow; the installed independent MixedLM, ICC and signal qualifications then passed. No Windows security policy was changed. The previous 2026-11-07 installer passed historical checks but lacked a source identity and was not reused. The first 2026-11-09 rebuild was also excluded after source-stamp collection failed; commit `5447b54` fixes that metadata call and the final build above passed.
- BENCH-01..06 results and accepted target deviations are recorded under G1. The existing protocol reports subprocess wall/worker timing and GUI gaps but does not collect per-process CPU utilization.
- The pre-existing line-ending-only edit to `data/synthetic/generator_manifest.json` remains uncommitted and byte-preserved.

Native parity map:

| Former web surface | Native replacement | Verification |
|---|---|---|
| Today, Athlete 360, Plan, Monitor, Test, Match/pose, Research and Reports | Direction F Qt Performance OS pages, docked Athlete 360, pyqtgraph viewers and direct `DynamisAppService` persistence | `tests/test_desktop.py::test_native_performance_os_workspaces_load_without_errors`, `test_native_performance_operations_edit_monitor_and_reports`; G3 native screenshots and benchmark |
| Research home, project/study authoring, cohort, plan, runs, evidence and report | Qt catalogue, native dialogs and five research workspaces | `test_native_project_and_study_creation_forms`, `test_native_cohort_and_plan_forms_support_freeze_fork_and_history`, `test_native_research_journey_executes_promotes_freezes_and_exports`, `test_authored_project_study_cohort_plan_and_report_versions` |
| Dataset pages and admission | Bounded `QAbstractTableModel` preview, provenance/rights inspector, native local-file admission, QC and quarantine history | `test_parquet_preview_is_bounded_and_offset_correct`, `test_native_admission_form_verifies_rights_runs_qc_and_admits`, direct `test_admission.py` checks |
| Scientific library | Qt catalog for metrics, protocols, methods and models, preserving prototype/unavailable status and limitations | `test_native_investigation_editor_and_report_version_comparison` checks the bundled catalog; the scientific test suite verifies the direct method contracts |
| Investigation blocks, run history, evidence and report workflow | Versioned Qt investigation editor; direct analysis tab; explicit evidence promotion; frozen report diff; clickable lineage DAG | `test_native_investigation_editor_and_report_version_comparison`, `test_native_research_journey_executes_promotes_freezes_and_exports` |
| Unsupported model simulations | Read-only `PROTOTYPE`/`UNAVAILABLE` registry state; no athlete prediction or injury-risk execution | Catalog status and limitation display; no model execution control is exposed in the native UI |

G4 has no remaining implementation work. The G1 MixedLM timing deviation remains recorded; its qualified numerical method and optimizer sequence are unchanged.

## Commits

Every implementation commit uses a `RES-604` subject. G1 base: `0377177` (`RES-604: implement native research workstation`); G1 evidence: `a02a108` (`RES-604: record native benchmark and G1 evidence`). G2 service: `1c4d8c6`; G2 UI: `fd29072`; G2 evidence: `92ca8e8`. G3 service: `f27953d`; G3 native visual/workflow: `df59eac`; G3 screenshots and benchmarks: `7a25fdb`. G4 includes transport decoupling `4b318ef`, Windows build tooling `9e98590`, package/recovery evidence `813bdc3`, research parity `e3cc02b`, web retirement `139e45f`, qualification runner `fc268f9`, performance evidence `527e815`, and lazy-load/frozen-visual verification `7d4218f`. One G1 MixedLM timing deviation remains visible with the qualified optimizer sequence unchanged.
