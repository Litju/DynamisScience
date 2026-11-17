# RES-621 longitudinal research workflow development

## Baseline captured 2026-11-17

Source before implementation: `694e0ef`. Actual Windows PySide6 window,
1366×720 client geometry; isolated synthetic store, 20 athletes, 12 weeks.
This is development evidence, not release qualification or efficacy evidence.

The reproducible case is `services/science/scripts/res621_study.py`. It calls
the existing seeded roster/force generator without dense traces, admits three
CSV batches through the existing importer, and creates protocols before admitting
their future observations. The schedule uses nonrandom coach assignments and
individualized supervised doses, replicated intervention/comparator periods,
four absent visits, a two-day delay with 75% adherence, and a future-period
amendment. Randomized onset is ineligible; no allocation or p-value is fabricated.

### Observed paths and friction

| Task | Observed original path | Reproduced problem |
| --- | --- | --- |
| Enter follow-up import | Add data → accept “Import a file” → import review | Extra choice modal before the normal primary task |
| Open individual experiment | Squad → athlete → nested Scientific investigations / Data | Individual research lives in a different perspective from cohort research |
| Review actual conduct | Visits and timeline | At this geometry only three timeline rows visible; visit entry below viewport; large history/summary compete with current conduct |
| Analyze protocol | Analyze this protocol → eligible method and contract | Existing positive behavior: selected protocol reaches analysis, explicit descriptive estimand and no causal uncertainty |
| Inspect results | Results → Result / Trajectory / Diagnostics | Explicit scientific qualification; result selector leads with method IDs; no local report handoff |
| Inspect series | Research Workbench → Series of experiments | Two selections; athlete/protocol absent from persistent context, though scope remains stored; default Data pane repeats internal fields and consumes width |
| Inspect data | Research Workbench → Dataset & Cohort → Parquet preview | Internal IDs precede the outcome; no immediate human-readable QC summary |
| Reopen report | History → frozen report | Existing frozen preview/export works; modal mixes reports, revisions, runs and every visit-driven investigation version |

Evidence captured and inspected in this run (outside repository):
`D:/SWE_HOME/codex_home/artifacts/res621-before/01-native.png` (workspace),
`02-native.png` (visits), `03-native.png` (analysis), `04-native.png` (result),
`05-native.png` (series), `06-native.png` (data).
Computer Use also inspected import entry and frozen-history modal directly.
Screenshots do not establish screen-reader compatibility or full accessibility
compliance. Native keyboard and geometry checks are covered separately below.

## Gate A: context and navigation

Added persistent scope and research-stage selectors using the existing Qt shell.
The workspace revision, athlete investigation and saved protocol/result binding
remain available across individual, cohort data and series tasks. Stage selection
restores after append/reopen using per-store settings. Add data directly opens
import; Research retains the admitted-dataset attachment alternative.

The append integration test reproduced a background eligibility request against
the old revision while clearing the prior form. Suppress requests during that
transition and invalidate earlier eligibility callbacks; fresh eligibility still
uses the active revision. No numerical implementation changed.

Gate A scoped validation: `scripts/scoped_tests.py tests/test_research_workflow.py
tests/test_native_experiments.py tests/test_longitudinal_research.py -q`: **14 passed**,
3,060,599 sampled peak scratch bytes, guarded scratch removed. The first attempts
exposed the old-revision eligibility modal; the corrected complete scope passed.
Three interrupted diagnostic scratch roots were subsequently removed after their
processes exited, using exact resolved paths under the runner's temp parent.
The native baseline used 7,578,406 peak bytes and was removed on normal exit.

Before/after task paths are recorded in Gate B below.

## Gate B: conduct, results and historical research

Actual-visit entry and the selected-protocol analysis action now appear together
above the timeline. Conduct counts distinguish measured, missing and unrecorded
visits; a row opens its actual record for explicit correction. The period summaries
and append-only visit ledger remain available behind a disclosure control. Actual
exposure is still entered explicitly, and no planned condition is copied into it.
Actual-date figures label missing visits, deviations and incomplete adherence.

Results link directly to report creation and frozen history. The inline history
page filters reports and analyses by athlete, can broaden to the whole workspace,
and shows immutable content, figures and provenance without activating an earlier
revision. It does not rerun analyses. Cohort result summaries use the existing
scientific renderer; diagnostics and execution contracts remain in a separate tab.
The existing scratch-analysis ribbon, run actions and syntax bar are hidden on
research-task pages, where they do not apply. They remain available in the
original scratch-analysis view. Design E components, colors and numerical methods
are retained.

### Integrated demonstration

`tests/test_twelve_week_workflow.py` exercises the real MainWindow, import review,
protocol form, conduct entry, existing isolated analysis worker, series controls,
report export and a fresh MainWindow/service reopening the same persistent store.
The first six weeks and the bulk visit ledger are deterministic setup via existing
services; the follow-up admission, amendment, representative final visit, analyses,
second series and historical report are completed through native task actions.
This is an automated researcher journey, not a claim that 220 records were typed
manually or that a novice researcher completed a usability study.

It verifies one workspace, 20 athlete protocols, three revisions, 708 measured trial
rows over 12 weeks, 220 scheduled visit records including four missing visits,
two series captures and frozen cohort/individual report sections. It independently
recomputes all 11 scheduled SUB-001 session means from CSV using arithmetic means;
no production estimator is called for that reference. It rejects randomized onset
for this nonrandom study, preserves old run and comparison documents after the
future-period amendment, checks the historical report's exact exported bytes after
append and restart, and restores the selected athlete and history stage.

### Before/after task paths

These are navigation selections and modal transitions, not mouse-click counts or
timed novice-user measurements. A combo selection can itself require two clicks.

| Task | Original | Refactored | Verified benefit |
| --- | --- | --- | --- |
| Enter import | Add data → choose/accept Import → review | Add data → review | 2 task selections → 1; one choice modal removed |
| Individual result → series | Research Workbench → Series | Stage: Series comparison | 2 navigation selections → 1; athlete/protocol stay visible; the underlying perspective still changes once |
| Record actual visit | Scroll below visible timeline/summary → expand entry | Visible record/correct control or open a timeline row | Entry no longer requires finding the offscreen action at 1366×720 |
| Read frozen report | History modal; mixed types and all investigation versions | Inline Frozen history; athlete filter, report/run type selector | No history modal; preview does not select a data revision |
| Interpret cohort result | JSON on reopening; contract repeated below result on execution | Existing scientific summary; separate diagnostics/provenance | Technical details preserved but removed from default reading path |

Original screenshots were captured from the Windows application. Refactored
screenshots and task completions were captured with offscreen Qt. **Computer Use
was stopped by the user with Escape before the refactored physical-display
walkthrough**; no further desktop input was sent. Therefore these improvements are
verified by task execution and Qt rendering, with final physical Windows acceptance
still outstanding. The interrupted synthetic native process was stopped and its
owned marked scratch root was recovered and removed (7,578,406 bytes).

Refactored evidence: `D:/SWE_HOME/codex_home/artifacts/res621-qt-after/`.
The harness explicitly loads installed Segoe UI fonts for offscreen rendering;
the initial missing-glyph captures were rejected and replaced. Screenshots cover
amendment, appended revision, actual observations, descriptive result, ineligible
randomized inference, series, frozen report, restart and compact geometry.

### Validation and remaining limitations

Gate B's 10-file scientific/native regression scope passed **34 tests in 125.98 s**,
with 27,574,731 sampled peak scratch bytes and complete guarded cleanup. A preceding
run exposed a missing-label rendering error (mixed date/axis coordinates); the
corrected run additionally draws the Matplotlib canvas. The original QC/deviation
marker remains identifiable and now explains its reasons. Scientific algorithms,
catalogue definitions, database schema and immutable report bytes were not changed.

Final focused validation: `scripts/scoped_tests.py tests/test_twelve_week_workflow.py
tests/test_research_workflow.py tests/test_native_method_suite.py
tests/test_workbench_panes.py -ra`: **24 passed in 52.04 s**, 8,462,864 sampled
peak scratch bytes, scratch removed. This covers task-mode visibility, explicit
scope→stage keyboard order, navigation preserving an unsupported method choice,
fresh-window history restoration and compact 911×480 logical geometry. Offscreen
geometry is not actual Windows 150% DPI. At compact width, the context toolbar can
place binding details in overflow; the selected protocol remains in the task page.

The broader scratch-workbench check initially timed out attempting an unsupported
alpha=0.1 rerun. Its test now changes the supported contrast instead; the fixed
95% engine contract is unchanged. `scripts/scoped_tests.py
tests/test_workbench_integration.py -x -ra`: **7 passed in 64.84 s**, 59,768,801
sampled peak bytes, scratch removed. Two earlier copies retained Windows read-only
snapshot flags and required guarded cleanup recovery. The scoped runner now clears
read-only attributes only after proving the target is inside its owned scratch root.
It retains the same 512 MiB / 300 s limits and protected-data boundaries.

The final report-export layout check ensures the frozen-export action is inside
the visible window and clicks it through Qt input, then checks exact historical
bytes. `scripts/scoped_tests.py tests/test_twelve_week_workflow.py
tests/test_research_workflow.py tests/test_native_report_history.py -ra`:
**4 passed in 51.53 s**, 10,184,923 sampled peak bytes, scratch removed.
The retained `journey-receipt.json` contains the exact workspace, revision, run and
comparison identities and matching original/reopened report SHA-256 digests.
`week6-frozen.html` and `week12-frozen.html` retain the small synthetic reports;
the databases and admitted measurement stores are removed after the test.
The artifact-retention replay of `tests/test_twelve_week_workflow.py -ra` also
passed: **1 passed in 34.54 s**, 7,668,593 sampled peak bytes, scratch removed.

Remaining limits: report templates still include generic workspace-level metadata
before individual scientific sections; very wide scientific tables require
horizontal scrolling; protocol authoring still uses a substantial form; the older
explicit revision-switching History modal remains available; bulk conduct import
is not introduced. The data preview still exposes technical column names beneath
its source/QC summary. No causal treatment estimate, forecast or imputation is added.
No claim of screen-reader or full accessibility compliance is made. Physical
Windows after-verification remains incomplete following the Computer Use stop.

The owner's generator manifest stays unstaged with SHA-256
`835398DA594421BC9F04647992B0E9CEFD5DC844FD931D1964896B2E164A2587`.
All measurement/database writes were directed to disposable roots outside the
checkout and `D:/datasets/DynamisScience`. No push, merge, reset, migration,
release packaging or operational dataset mutation was performed.

## Focused native simplification continuation

The subsequent [RES-621 native simplification record](RES-621_NATIVE_SIMPLIFICATION.md)
addresses the remaining roster/comparison width, technical preview, protocol-form
and toolbar issues above. It retains native Qt before/after evidence and scoped
regressions, including the existing 20-athlete journey. Verification remains
offscreen Qt; no physical Windows after-acceptance is claimed.
