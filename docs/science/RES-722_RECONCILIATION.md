# RES-722 Research Data Reconciliation

Open a persistent research workspace with an admitted CMJ summary, then choose **Add data** or **Data Workspace → Reconcile follow-up**. Choose an export and compare **Discrepancies**, **Identities**, **Session QC**, **Trial changes**, and **Source preview**. Use the original testing log to confirm athlete, session, source, instrument, and protocol details. Record a reviewer and reason, then select **Approve**, **Reject**, or **Quarantine**. After approval, **Open revision in Analysis** opens the admitted measurements in the same workspace. The review picker retains the proposal and decision versions. The standard importer remains available for initial data and other measurement families. [RES-722](https://linear.app/alignerr-cmj/issue/RES-722/dynamisscience-research-data-reconciliation-and-session-identity)

## Reproduced task comparison

Both paths used the same deterministic synthetic roster of 20 athletes, baseline at study week 1, and follow-up at week 12. The follow-up renamed athlete A07, renamed session labels and source columns, declared jump height in millimetres, and included one amended baseline trial, B01. Two additional files supplied the baseline duplicate and the incompatible protocol.

| Task | Original workflow at `f8a962639c683a788ca17ca640343d36dc530eec` | Native reconciliation |
| --- | --- | --- |
| Identify duplicates and units | RES-636 recognized the duplicate and normalized F07 to 35.5 cm. It retained `A07-renamed` as a separate identifier in that admission. | The review showed the byte-identical duplicate and the source header and unit differences. The reviewer rejected the duplicate and kept the original export. |
| Exclude the incompatible protocol | Append refused the incompatible protocol after standalone admission, reporting `Incompatible or missing protocol_id; attach separately`. | The reviewer saw the incoming protocol ID against the reference and quarantined it before admission into the workspace. |
| Apply roster, session and measurement corrections | Append refused the original mixed export with `Overlapping trial_id records; attach the batch separately`. The replay wrote two CSVs. It reconciled the renamed athlete and follow-up session and removed the overlapping row in one export, then corrected B01 in a copy of the baseline. It attached the corrected baseline separately and appended the prepared follow-up. | The reviewer selected A07 for the alias, mapped the two session labels, confirmed source context, reviewed 20 new trials and one correction, and approved the original file. |
| Reopen and analyze | The replay produced three data revisions in the same workspace. | The native journey produced two data revisions in the same workspace. Reimport returned the existing approval. A reopened window ran the existing descriptive method against the corrected revision. |

Both routes returned 40 observations for 20 athletes. The independent fixture means are 35.275 cm for week 1, including the B01 correction from 30.5 to 31 cm, and 37.25 cm for week 12. The pre-change source replay performed actual CSV edits in a disposable copy. The comparison records steps and outputs, without a timing estimate or claim about Excel usage.

## Evidence and reproducibility

The native acceptance test drives the real PySide6 widgets with synthetic inputs. The Qt harness supplies file paths to the picker and uses the native review dialogs, decision controls, and Analysis button. Separate tests verify approval and reuse across a fresh Python process, source and historical snapshot checksums, frozen report bytes, SQLite migration and integrity, rights, row and session QC, malformed input, and approval retry after an injected decision-write failure.

From `services/science`, run the three acceptance files through the existing scratch-bounded test launcher.

~~~powershell
.venv/Scripts/python.exe scripts/scoped_tests.py tests/test_reconciliation.py tests/test_reconciliation_baseline.py tests/test_native_reconciliation.py -s
~~~

The test for the original workflow obtains the pre-change files with local `git archive` and runs them in a separate data root inside the test's scratch directory.

The marked regression run `eee5ddd9bc994276be3b41ed2340459a` passed all 132 scoped tests with a sampled scratch peak of 31,859,420 bytes. The protected dataset tree fingerprint matched before and after both marked runs, and the working generator manifest retained SHA-256 `835398da594421bc9f04647992b0e9cefd5dc844fd931d1964896b2e164a2587`.

The repeated acceptance run `b02f625f535d4f35b71dd4380b37cd29` passed through the Windows Qt renderer and captured batch `REC-59BD604A7FC605793FD5`, workspace data revision `DATA-U-4970824C`, and analysis run `RUN-U-0002`. The fixture IDs are scoped to that disposable run.

- [Pending discrepancies and context](res722-evidence/res722-01-review.png)
- [Approved correction and new trials](res722-evidence/res722-02-approved.png)
- [Eligible analysis on the reopened workspace](res722-evidence/res722-03-analysis.png)

## Scientific scope

This acceptance covers vendor-neutral CMJ trial summaries in the existing RES-636 parser, with CSV, Excel and Parquet exercised. Review requires a compatible canonical schema, recorded study weeks, a matching instrument, protocol, sampling rate and research rights. Where a baseline includes dates, the review also checks ISO dates against existing session IDs. Unknown athlete labels require a reviewer-selected existing roster ID. Session mappings and missing source context require testing-log evidence. Stored aliases are scoped to the workspace and source.

A correction changes measured values for the same trial, athlete, session and study week. The previous input snapshots and frozen reports remain addressable. Raw traces, new roster enrolment, cross-protocol pooling, and vendor-specific calibration qualification are outside this slice. The synthetic descriptive results demonstrate ingestion and analysis continuity. Individual meaningful-change thresholds, device agreement, causal effects, and calibration validity require separate evidence. [Practitioner Data-to-Decision roadmap](https://linear.app/alignerr-cmj/document/dynamisscience-sportsagentslab-practitioner-data-to-decision-roadmap-054b3b3e3216)

## Implementation commits

- `62e5d475aac44edb5fb9a043c52a8c7d866b4dd0` persists source mappings and immutable correction revisions.
- `8b8d8fb62120b33c2c4f267448e370cabcd5de02` integrates review and Analysis in Data Workspace.
- `a07aef60d4b6f03a0f29ab462e8b702714b38716` covers mixed units, timing and format edge cases and replays the pre-change workflow.
