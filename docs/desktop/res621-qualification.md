# RES-621 qualification — in progress

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

All tests above used pytest temporary data roots. An intermediate full suite at `38e4c2b` was interrupted for the Run-button repair; it is not a passing receipt.

Full source regression at `af97919db1945b8705839ca7639f6afd351add1d`: `QT_QPA_PLATFORM=offscreen uv run pytest`, **174 passed in 208.83 s**. This is an automated source result, not installed-app or on-screen qualification. At that point the only pre-existing tracked modification remained the generator manifest, with the same SHA-256 as above; this report was untracked.

## Open qualification and defects

- **P1 — valid synthetic admission remains unproved.** Existing QC requires `CALIBRATED` even for a fixture-only source; the earlier `SIMULATED` instrument was correctly quarantined. The repository's ignored test fixtures contain a `CALIBRATED` test label but no independent physical calibration evidence. No physical calibration is claimed here; a defensible synthetic admission demonstration remains necessary.
- **Admission units require operator qualification.** The changed code checks and converts its supported mass, time and distance units and compares them with protocol metadata; unsupported units are rejected. This is not a claim that arbitrary units or all measurement fields are supported.
- An independently rendered synthetic HTML report was inspected in headless Edge over loopback HTTP. Its recorded change `0.07616275000000017` and final-point mean interval `1.734291839839779–1.8654102315887926` match the source run. The first viewport was inspected; this is not the complete installed report journey or a general report qualification.
- The requested valid and invalid native admission demonstrations, study authoring and reopening, scientific comparisons, evidence/report journey, figure inspection, accessibility checks and source-matched installer workflow have not been completed in this campaign.
- Historical source records and snapshots were not rewritten. The new source-binding rule does not repair any pre-existing incorrectly associated artifact. Concurrent admission and interrupted snapshot creation still require assessment.
- The prior RES-620 evidence records compact 3D, high-DPI hardware and load-sensitive journey-test limitations; they have not been requalified here. The checkbox change has only offscreen visual evidence so far.

No current installer hash or installed-workflow receipt is claimed. Do not close RES-621 on this record.
