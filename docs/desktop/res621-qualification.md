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

All tests above used pytest temporary data roots. An intermediate full suite at `38e4c2b` was interrupted for the Run-button repair; it is not a passing receipt.

Full source regression at `af97919db1945b8705839ca7639f6afd351add1d`: `QT_QPA_PLATFORM=offscreen uv run pytest`, **174 passed in 208.83 s**. This is an automated source result, not installed-app or on-screen qualification. At that point the only pre-existing tracked modification remained the generator manifest, with the same SHA-256 as above; this report was untracked.

## Open qualification and defects

- **P1 — valid synthetic admission remains unproved.** Existing QC requires `CALIBRATED` even for a fixture-only source; the earlier `SIMULATED` instrument was correctly quarantined. No physical calibration is claimed here. A defensible, explicitly synthetic fixture and QC treatment must be established without weakening checks for real data.
- **P1 — admission unit contract requires further verification.** The CMJ and sprint validators and harmonizers do not consistently validate or apply every declared unit before range checks. Do not treat the current admission path as fully qualified for arbitrary unit declarations.
- The requested valid and invalid native admission demonstrations, study authoring and reopening, scientific comparisons, evidence/report journey, offline HTML rendering, figure inspection, accessibility checks and source-matched installer workflow have not been completed in this campaign.
- Historical source records and snapshots were not rewritten. The new source-binding rule does not repair any pre-existing incorrectly associated artifact. Concurrent admission and interrupted snapshot creation still require assessment.
- The prior RES-620 evidence records the checkbox tick, compact 3D, high-DPI hardware and load-sensitive journey-test limitations; they have not been requalified here.

No current installer hash or installed-workflow receipt is claimed. Do not close RES-621 on this record.
