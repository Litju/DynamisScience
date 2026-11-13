# RES-644 — Persistent Research Workspace

Implementation branch: `codex/res-644-persistent-workspace`, based on merged `origin/main` `2e9f53cdaef361fedeedb18c0d41e3ce25ba28e8`. PR #2 and RES-621/636/613 were reviewed before implementation. No push, PR creation, merge, reset, installed-app launch or installer execution was performed.

## Implementation contracts

- A title creates one workspace in the existing `entities`/`entity_versions` store. It has a normal stable `STUDY-U-*` identity and a `workspace` marker. No dataset, project wizard, cohort, metric or plan is required. Legacy project/study/monitoring APIs remain available.
- Schema version 2 adds only `workspace_revisions`; schema creation is repeatable and transactional. Existing tables and historical documents are retained. A workspace is its own report/project context without creating a second user-facing project.
- Every attachment appends a `DATA-U-*` revision with its parent, ordered number, exact input snapshot IDs, full captured snapshot/source/admission/QC/provenance manifests, checksums and explicit compatibility decision. Admitted snapshot identities are the immutable batch identities; source-artifact and admission-record IDs remain in the captured inputs. The active revision and selected analysis are persisted in the workspace document and its version history.
- Separate attachment is the default and changes only the analytical selection. It never pools datasets. Compatible append currently supports admitted CMJ summary batches. It requires explicit confirmation that participant identifiers have the same meaning, matching source/rights, family, schemas/canonical units, registered instruments/protocols and available sampling/timebase metadata. Conflicting participant metadata or overlapping trial IDs are rejected. Other families remain separately attachable; unsupported pooling is rejected.
- Appended data is materialized once under the disposable/user research store, with its own Parquet checksums, while retaining the original immutable inputs. Transaction failure cannot expose a partially attached revision. A failure before commit may leave an unreferenced derived directory; it is never selected or admitted as evidence.
- Analysis preparation captures the expected revision inside one SQLite transaction, creates/freezes cohort and analysis-plan/spec versions through existing scientific services, then computes outside that transaction using captured objects. Missing measured time-axis metadata is rejected before any analysis context is committed. Methods, numerical routines and validation thresholds are unchanged; automatically captured plans explicitly remain non-prospective.
- Runs record workspace ID, revision ID, exact input IDs, snapshot, cohort/plan IDs and versions, qualified method/version, parameters, digest and execution provenance. New data does not rewrite old runs or make them current. Completion guards cover workspace/revision changes, including descriptive workers that finish against the same snapshot/table.
- Ordinary Export report resolves the selected saved run, rejects wrong-revision, exploratory or unverified evidence, applies existing evidence/citation services, captures/freezes a new report version transactionally and exports HTML. Earlier versions/citations/figures/limitations remain immutable. Historical HTML rendering uses captured frozen context without resolving or recomputing current data.
- History lists data revisions, saved runs and full frozen report records. Selecting a revision/run restores its exact data, compatible design and saved analysis; an earlier run is never re-executed merely by opening it.

## Commits

- `102e5ab3bfaac9074a3b8e9a4a40db2896846acf` — persistence, transactional revision/run/report contracts; four lifecycle/failure/migration tests.
- `df9e9519d38bbdfdab3f652b1d0dfe794221df86` — native Create/Open/Add data/Analyze/Export/History actions, selection restoration, source-native walkthrough and additional rollback/missing-metadata/Qt tests.
- `951c3600fca04b85aba393bb1eecd8c7d5e0cbc6` — restore compatible design when revisiting revisions; reusable portable fixture/profile preparation, with no pre-created workspace or dataset.

- `a3e62440d6b6d313f4287a644782cdf206eefae1` — reject stale descriptive/exploration completions even when snapshot/table identity stays the same; 14 scoped workspace/integration tests passed.
- `7a68003` — clamp History to the available high-DPI work area, with native geometry assertions.
- `ed5f54a98bcce159a10bfc1628551dffada11946` — preserve the previously captured input manifests when appending; explicitly reject changed captured instrument/calibration metadata. Seven scoped workspace tests passed.

- `18494d5eb3afe8831a8c1de6f09c5bac5ec67630` — bind reliability cohorts to the selected activity instead of the default Walking activity. Added a real-data regression on a checksum-verified disposable MoveSmart copy: Running cohort and result both have eight participants. No numerical routine or threshold changed.

## Verification

**Final source `18494d5eb3afe8831a8c1de6f09c5bac5ec67630`: 290 passed in 360.84 seconds.** [Final activity-corrected full regression log](res644-evidence/activity-regression.log) and [receipt](res644-evidence/activity-regression-receipt.json). This includes the existing scientific/Qt/legacy suite, seven persistence/workspace tests, and the additional selected-activity regression.

Preceding implementation `ed5f54a98bcce159a10bfc1628551dffada11946`: **289 passed in 403.32 s**, with `QT_QPA_PLATFORM=offscreen` for the automated Python/Qt/scientific suite and real native Windows walkthroughs separately. [Full final regression log](res644-evidence/final-regression.log). No test timeout, numerical tolerance or validation threshold was changed.

An intervening run had 288 passes and one existing five-second Qt wait timeout during legacy monitoring creation while other native GUI/build work was active. A parallel isolated native Qt attempt also exited with Windows RPC/access-violation diagnostics. Both are recorded as harness instability rather than hidden as passes; the clean full run above passed all 289, including the legacy case.

- Initial baseline attempt: 278 passed, four setup errors because D: filled while copying private snapshots into disposable test stores. No scientific assertion failed in that attempt. Automatic approval review rejected cleanup of that run's temporary directory as “blocked by policy”; no alternate deletion was attempted. Subsequent regression runs used C: for all three temporary-directory environment variables.
- Complete regression at `df9e951`: **289 passed in 443.79 s** (original 282 plus seven workspace tests). A preceding complete run passed 286 before the additional tests were added. Pytest reported Windows temporary-directory cleanup warnings after passing; those warnings do not indicate research-store corruption.
- Source-native Windows Qt journey: [100% receipt](res644-evidence/source-100/receipt.json), [125% receipt](res644-evidence/source-125/receipt.json), [150% dark receipt](res644-evidence/source-150/receipt.json). All three final source receipts identify implementation commit `ed5f54a98bcce159a10bfc1628551dffada11946`. Each records one stable workspace ID, two genuine ETL/admission batches, two data revisions, two immutable runs, report export without manual freeze, window close/reopen, history and earlier-run inspection. Screenshot hashes are in each receipt. The source script restarts the window/service in-process; the portable walkthrough below separately verifies an actual process restart.
- Available desktop work area bounds source windows to 1366×720 logical pixels at 100%, 1093×576 at 125%, and 911×480 at 150%. The source test targets a 1366×768 desktop and preserves the taskbar/work-area boundary; it does not claim a 768-high available work area.

Reproduce from `services/science` with `PYTHONPATH` set to that absolute directory:

```powershell
$env:TEMP='C:/Users/Usuario/AppData/Local/Temp'
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
$env:QT_QPA_PLATFORM='offscreen'
uv run pytest
Remove-Item Env:QT_QPA_PLATFORM
$env:QT_SCALE_FACTOR='1.5'
uv run python scripts/res644_walkthrough.py ../../docs/desktop/res644-evidence/source-150 dark
```

## Portable native journey

The complete native UI journey ran in source-matched portable executable SHA-256 `b71cb00488f1bba6bc8f22c44834d806d36c169cef7d4416ed8f9ae1481aea38` at source `a3e62440d6b6d313f4287a644782cdf206eefae1`. All 49 packaged application modules were compared with compiled checkout source. No dataset or workspace was pre-created: the preparation script saved only synthetic files and a reusable scientific metadata profile.

Actual UI input created empty workspace `STUDY-U-4EB94E4E`, imported baseline and follow-up files through ETL/QC, explicitly selected compatible append, executed analyses on both revisions and exported two reports through the ordinary Export report action. The first process (13876) exited; a new process (5100) reopened the same store at 150% dark. History restored revision 1 and its stored run without recomputation. Two original run digests, two original report content hashes and the baseline HTML hash remained unchanged.

See [workflow receipt](res644-evidence/portable/workflow-receipt.json), [original build receipt](res644-evidence/portable/build-receipt.json), [baseline report](res644-evidence/portable/baseline-report.html) and [follow-up report](res644-evidence/portable/followup-report.html). Both HTML files were independently rendered in native Qt and checked for their saved run IDs, synthetic limitations and provenance. The high-DPI History button overflow found in this first package was subsequently fixed and asserted in the final source walkthrough; final package verification is recorded separately.

Preceding GUI-qualified clean package: [release build receipt](res644-evidence/portable/release-build-receipt.json), source `ed5f54a98bcce159a10bfc1628551dffada11946`, application Git tree `42e0d88ee42f7a2f7e4c9f684abbc9590a744da0`, all 49 packaged modules bytecode-equal to compiled checkout source. EXE SHA-256 `3ffb0b2dd77db0b0e1035a20ce1d8424fa5d573d0bb89efc3f1060461168972b`, 31,411,968 bytes. Executable: `C:/Users/Usuario/AppData/Local/Temp/res644-build-20261112/ed5-release/DynamisScience/DynamisScience.exe`. Earlier intermediate build caches were not trusted: clean new work/dist directories and the module comparison established final identity.

Final release requalification reused the same workspace store. At 150% dark it rejected append of a newly admitted dataset with a different protocol/sampling rate, preserving both revisions and both original runs/reports. It then selected revision 2, executed `RUN-U-0003` and exported a third immutable report without manual freezing. A fresh process reopened the workspace at 125% dark and showed the current revision, saved analyses and oldest frozen report. The corrected History button remained fully visible at both scales. The final release was also restarted and reopened at 100% on the maximized 1366×720 work area of the 1366×768 desktop. Original stored run and report document bytes were hash-compared before/after these actions. See [final package workflow receipt](res644-evidence/portable/final-package-workflow.json), [final report](res644-evidence/portable/final-release-report.html), [150% History](res644-evidence/portable/12-final-history-fit-150.png) and [125% restart](res644-evidence/portable/14-final-reopened-125.png).

Gate disposition: repository/requirements audit, title-only creation, repeated attachments, immutable revisions, scientific execution, automatic frozen export, reopen/history, regression/native verification and delivery evidence are demonstrated. No statistical algorithms or qualification thresholds changed. RES-613 owner/installed-product acceptance and RES-621/636 acceptance items remain separately tracked.

Final activity-corrected package: [final build receipt](res644-evidence/portable/final-build-receipt.json), source `18494d5eb3afe8831a8c1de6f09c5bac5ec67630`, application Git tree `ea91f9defa03cd6a3b7dc81bcc98f727eb034c07`. All 49 modules match compiled checkout source. EXE SHA-256 `30af38e4388719dba92d30fadbd64e9f6b59cc4b5b679b7242cd8c778143538d`, 31,412,048 bytes; executable `C:/Users/Usuario/AppData/Local/Temp/res644-build-20261112/activity-release/DynamisScience/DynamisScience.exe`.

The real packaged hidden-worker path executed qualified reliability for Running against a checksum-verified disposable MoveSmart copy. Its saved cohort and result both contain eight participants, with the exact revision, cohort/plan versions and digest retained. [Packaged Running proof](res644-evidence/portable/packaged-running-receipt.json). The activity correction does not change the UI or numerical methods.

The exact final activity-corrected executable also reopened original workspace `STUDY-U-4EB94E4E` at 150% dark, executed `RUN-U-0004`, exported another internally frozen report and displayed the original report v4 with its citations. There remains one workspace and two data revisions; four runs and four frozen report versions are retained. Every previously stored run/report document was hash-compared unchanged, and re-rendering the original frozen HTML with the existing Windows export newline convention produced the original SHA-256. [Final-build native GUI receipt](res644-evidence/portable/activity-gui-receipt.json), [final-build export](res644-evidence/portable/activity-corrected-release-report.html) and [final-build history screenshot](res644-evidence/portable/18-final-build-retained-baseline.png). All qualification windows were closed.

## Preservation and limits

The owner's manifest remains uncommitted and byte-preserved: SHA-256 `835398DA594421BC9F04647992B0E9CEFD5DC844FD931D1964896B2E164A2587`. The operational database was used only as a read-only source for existing checksum-verified test copies; its observed hash before/after portable qualification is `93EBB1EEA705AC879F02DAB56B499397780ACC75E8AB45FE39C06AA21F35EAEA`. All new mutations use disposable synthetic roots. No installed application was disturbed.

No individual-athlete branches, new adapters, statistical models, framework/database replacement or Direction E redesign. Automatic append is deliberately limited to the validated CMJ-summary contract; unrelated or unsupported data stays separate. Statistical eligibility still requires measured scientific metadata: no time axis, participant identity, instrument calibration, source rights or causal design is invented.
