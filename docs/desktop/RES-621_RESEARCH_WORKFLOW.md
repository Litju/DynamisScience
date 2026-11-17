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

Final before/after measurements are recorded after Gate B.
