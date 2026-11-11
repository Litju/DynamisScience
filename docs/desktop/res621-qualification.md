# RES-621 qualification

This is a partial engineering record, not product acceptance. RES-613 remains the owner acceptance gate.

## Starting state

- `main` at `3c795233f185badb16afa130cafe754c820918f3`, merged PR #1. Remote: `https://github.com/Litju/DynamisScience.git`.
- Pre-existing `data/synthetic/generator_manifest.json` modification: SHA-256 `835398DA594421BC9F04647992B0E9CEFD5DC844FD931D1964896B2E164A2587`. Preserved and excluded from commits.
- Work branch: `codex/res-621-research-workflow`. No push or merge.
- The source application was opened on Windows against a newly created temporary synthetic root and the admission dialog was inspected. This was not a completed operator journey.

## Changes and scoped checks

| Commit | Change | Verification |
| --- | --- | --- |
| `ef32796` | The native TEST_FIXTURE choice retains fixture-only provenance; rights checks still apply. | Admission and native dialog: 12 passed offscreen. |
| `4a67bd0` | Readable QC decision and retained reasons; sprint coordinate convention can be entered. | Admission and dialog: 13 passed offscreen. Full suite: 173 passed in 199.32 s. |
| `274b84d` | Prevent overwriting a snapshot with changed or unrecorded metadata and retain distinct QC assessments. | Admission, authoring and dialog: 16 passed offscreen. Legacy snapshots without recorded metadata fail closed on repeat admission. |
| `38e4c2b` | Bind new source-artifact identity to the source, retaining matching existing records. | Admission and authoring: 15 passed offscreen. |
| `af97919` | Add a visible first-run button to the Results header. | Workbench pane and theme checks: 27 passed offscreen. |
| `66171a8` | Validate supported input units and normalize CMJ and sprint values before range checks. | Admission, authoring and dialog: 18 passed offscreen. |
| `54e5947` | Allow instrument and protocol IDs to match the source file. | Native dialog: 2 passed offscreen. |
| `642519a` | Restore native checkbox indicators by removing the indicator styling override. | Workbench checks: 27 passed; offscreen images show ticks in light and dark themes. |
| `f00bdc0` | Check instrument family, protocol units and sampling; report malformed sampling and week values. | Admission, authoring and dialog: 20 passed offscreen. |
| `8f158fd` | Route admitted synthetic fixture reads to their own snapshot and do not depend on the bundled fixture. | Admission, authoring and dialog: 19 passed offscreen, including exact source-row checks. |
| `7acb969` | Identify the statistic represented by report intervals, including historical final-point intervals. | Lifecycle and authoring: 13 passed; offline synthetic report rendered and compared with its run. |
| `82de2f5` | Capture frozen research context and use it when exporting; warn for legacy versions without captured context. | Lifecycle, authoring and result checks: 23 passed. |
| `e0a2bd3` | Render ICC as dimensionless and retain the force unit for typical error. | Lifecycle, authoring and result checks: 24 passed. |
| `e3e9a37` | Allow GUI regression fixtures to use an explicitly selected disposable research copy. | Three Mendeley/MoveSmart checks passed using a verified copy. |
| `1d87286` | Reject empty or unidentified input records and non-finite sampling frequencies. | Admission checks: 18 passed. |
| `50fe83a` | Use recorded provenance for live descriptives and disclose that quality-flagged rows are included. | Three focused workbench tests passed. |

Tests mutated pytest temporary roots. Earlier runs also opened the operational database with SQLite's read-only online-backup API; in WAL mode that may touch its shared-memory index. A complete before/after hash of the private root was not captured. Subsequent real-snapshot GUI regressions can use the independently verified disposable copy instead. Intermediate full runs interrupted for further fixes are not passing receipts.

Full source regression at `af97919db1945b8705839ca7639f6afd351add1d`: `QT_QPA_PLATFORM=offscreen uv run pytest`, **174 passed in 208.83 s**. This is an automated source result, not installed-app or on-screen qualification. At that point the only pre-existing tracked modification remained the generator manifest, with the same SHA-256 as above; this report was untracked.

Full source regression at `e3e9a37` (application source through `e0a2bd3`): **179 passed in 184.21 s** with `DYNAMISSCIENCE_TEST_SOURCE_ROOT` set to a verified disposable copy. Direct raw-source comparison tests still read source files without modifying them. Later application changes require another full run.

## Open qualification and defects

- **P1 — valid synthetic admission remains unproved.** Existing QC requires `CALIBRATED` even for a fixture-only source; the earlier `SIMULATED` instrument was correctly quarantined. The repository's ignored test fixtures contain a `CALIBRATED` test label but no independent physical calibration evidence. No physical calibration is claimed here; a defensible synthetic admission demonstration remains necessary.
- **Admission units require operator qualification.** The changed code checks and converts its supported mass, time and distance units and compares them with protocol metadata; unsupported units are rejected. This is not a claim that arbitrary units or all measurement fields are supported.
- An independently rendered synthetic HTML report was inspected in headless Edge over loopback HTTP ([first viewport](res621-evidence/synthetic-report-offline.png)). Its recorded change `0.07616275000000017` and final-point mean interval `1.734291839839779–1.8654102315887926` match the source run. A later newly frozen version remained byte-identical when the study title changed. This is not the complete installed report journey or a general report qualification.
- The real Windows source application, on a new synthetic root, displayed a descriptive result after the operator selected a numeric variable and clicked the new Run control ([screenshot](res621-evidence/native-descriptives-run.png), 1366×720 work area). Checked options had visible ticks. The later row-scope label change is not present in that screenshot.
- The requested valid and invalid native admission demonstrations, study authoring and reopening, scientific comparisons, evidence/report journey, figure inspection, accessibility checks and source-matched installer workflow have not been completed in this campaign.
- Historical source records and snapshots were not rewritten. The new source-binding rule does not repair any pre-existing incorrectly associated artifact. Concurrent admission and interrupted snapshot creation still require assessment.
- An existing DynamisScience installation has the same Inno Setup identity; a normal installer test could replace its uninstall registration or close the running app. Installed-app qualification needs isolation that preserves it.
- The prior RES-620 evidence records compact 3D, high-DPI hardware and load-sensitive journey-test limitations; they have not been requalified here. The checkbox change has only offscreen visual evidence so far.

No current installer hash or installed-workflow receipt is claimed. Do not close RES-621 on this record.

## Final campaign (2026-11-11)

| Item | Result |
| --- | --- |
| `6531e75` | A FIXTURE_ONLY source may use a SIMULATED instrument and is admitted as `SYNTHETIC_ONLY` (record states `calibration=SIMULATED/NOT_APPLICABLE_TO_TEST_FIXTURE`, `empirical_validity=false`, `evidence_eligible=false`). Real-data QC is unchanged: the same SIMULATED instrument on a rights-verified non-fixture source is still QUARANTINED. 20 admission tests passed. |
| Native admission (real `MainWindow` + `DatasetAdmissionDialog`, Windows Qt platform, disposable root, existing fixtures `cmj.csv`/`bad.csv`) | Valid TEST_FIXTURE: QC ADMITTED, snapshot `DS-ADMITTED-*` created, reads its own Parquet (2 rows, synthetic=true, real=false), repeat admission returns the same record. Invalid `bad.csv`: REJECTED, "missing required columns: instrument_id, protocol_id, sampling_hz, session_id", no snapshot. Real-claim source with SIMULATED instrument: QUARANTINED, "instrument … calibration is SIMULATED", no snapshot. Each artifact keeps its own source ID. Screenshots: `res621-evidence/valid-synthetic-*`, `invalid-rejected-*`, `quarantine-real-claim-*`, `main-window-after-admission.png`. Dialogs were driven programmatically, not by mouse. |
| Long jobs | There is no Cancel control. Analyses run in an isolated worker process; the run record is written only after computation, so a failed worker leaves no run, evidence or temp file (`test_failed_isolated_worker_leaves_no_run_or_evidence`). The status line now says the analysis cannot be cancelled and the window stays usable. No estimator, optimizer or tolerance changed. |
| Full regression at `ac650cd` | **261 passed** (pytest exit 0) with `QT_QPA_PLATFORM=offscreen` against a verified disposable copy of the research root (SQLite integrity ok; 1841 content files hash-identical to the source; the private root was re-hashed afterwards: 0 mismatches, integrity ok). Includes the Mendeley MixedLM and MoveSmart ICC checks against R references. |
| Installed-package reproduction | Slope 0.9984512135, ICC(3,1) 0.8887265872, CI 0.7451953776–0.9692965400, typical error 75.7826 N, from the packaged worker on a disposable copy; digests equal the direct source runs. |
| Package | Source commit `116bc2d274efffef94b428699b3909c27a513cb0` (working tree: only the owner's `generator_manifest.json` modification, diff SHA-256 `D0691F70663717FC86A4D9AB51AD62650903F0F3D19AB21457FABEB593DDBF4B`). Installer `DynamisScience-RES621Test-Setup-x64.exe`, SHA-256 `A837AD47CF66D42E65D8A48F4DC1CD99A76A68C43EB4A691A3A374D90BC16B7B`, 142,756,515 bytes; bundle 585,426,722 bytes. Test identity: AppId `{5B1E2C4A-7D3F-4E8B-9A61-0C2D4F6A8B13}`, name "DynamisScience RES621 Test", dir `DynamisScienceRES621Test`. |
| Installer qualification (`test_windows_installer.ps1 -TestIdentity`) | PASS: onedir and installed startup to catalogue (3.9–7.0 s, no listening ports), Performance page, reopen, packaged workers for synthetic/Mendeley/MoveSmart with matching digests, Matplotlib PNG/PDF/SVG exports with embedded result digest, SQLite backup/restore (integrity ok, logical hash preserved, operational DB unchanged), uninstall removing app files while the research DB hash is unchanged. HKCU uninstall registry listing identical before and after. No DynamisScience registration was found in HKCU/HKLM or `%LOCALAPPDATA%\Programs` on this machine, so non-interference was shown by separate identity and an unchanged registry, not against a live production install. |

## Remaining limitations

- The installed executable was exercised by its scripted smoke/worker/export/recovery harness, not by an operator clicking the full journey inside the installed window; native on-screen clicking was done on the source application only (descriptives Run, earlier) and admission dialogs were driven through Qt calls.
- The Dataset → … → Reopen journey is covered by the automated Qt regression (including freeze/fork, supersession, UNVERIFIED method versions, frozen report context); it was not re-driven by mouse in this campaign.
- Figures/HTML were inspected in the earlier campaign (see above); no new figure inspection was made after `e0a2bd3`.
- Legacy snapshots without recorded admission metadata still fail closed on re-admission.
