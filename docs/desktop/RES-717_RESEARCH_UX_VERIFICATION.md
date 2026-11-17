# RES-716 / RES-717 native research verification — 2026-11-17

## Scope and observed journey

Used the completed synthetic demonstration at
`D:/SWE_HOME/codex_home/artifacts/res716-onset-demo-20261116-ready`.
Opened the actual PySide6 application on the Windows display, selected its workspace,
opened SYN-A from the squad, and inspected Scientific investigations → Protocol →
Visits and timeline → Analysis → Results → Trajectory → History → original report v6.
Repeated the relevant screens after restarting with the changes. Existing original
and amended results were inspected without drawing, importing or executing new runs.
Both athletes' execution/report flows were exercised in isolated Qt regressions.

The retained demonstration simulates future-dated conduct conditional on a real app
draw. It is an algorithm and persistence demonstration, not empirical intervention
evidence or completed prospective follow-up.

## Concrete friction and focused corrections

| Observed friction | Native correction |
| --- | --- |
| Frozen allocation fields appeared editable, leading to avoidable save errors | Allocation procedure, support, schedule and condition definitions are read-only after allocation; design and assumption controls are disabled; narrative amendment fields remain editable with existing backend validation |
| Manual period actions remained available for app-generated onset phases | Hide add/remove period actions for randomized onset; retain generated phases for inspection |
| Long phase and exposure strings displaced means and QC information | Bound initial timeline column widths, put means next to status, wrap occasion/time over two lines, and retain full values in tooltips; columns remain resizable and horizontally scrollable |
| Analysis action required scrolling past the timeline and summary | Place “Analyze this protocol” directly after the protocol-version selector; it retains that selected version |
| A dozen entry controls competed with conduct review | Expand “Record or correct an actual visit…” when needed; actual condition remains explicitly unknown until recorded |
| Phase colors alone carried the chart distinction; allocation was absent | Add intervention triangles and a dashed **planned** onset marker from the frozen allocation; actual dates and observed descriptive means remain separate |
| “Two-sided” did not spell out the tail convention | State inclusive absolute-statistic comparison, ties, observed allocation, denominator and support resolution; distinguish from doubling a signed tail |
| History showed report JSON with no usable report action, after dozens of visit-driven investigation versions | Preview frozen report content and export the selected version through existing services; list frozen reports first |

No persistence schema, statistical registry, new estimator, report format, external
dashboard or global navigation redesign was added. Frozen report content is retained,
including its original workspace-level template metadata; individual experimental
sections carry the captured randomized protocol, allocation and observations.

## Independent scientific check

Read-only SQLite inspection independently enumerated assignment-mask weights using
rational arithmetic, with no call to the production evaluator. Every assignment score
matched all three frozen runs. SYN-A original and amended runs each have +8 cm,
1 extreme assignment among 26, p=1/26. SYN-B has 0 cm, 26/26, p=1.
See [the method contract](../science/RES-716_RANDOMIZED_ONSET.md) for the exact tail,
new asymmetric hand example, assumptions and scientific limits.

Planned allocation, actual condition/exposure, visit deviations/corrections and
protocol amendments remain distinct fields and histories. Existing negative tests
still withhold p-values for missing/QC-ineligible schedules and for allocation,
timing, adherence, condition or deviation violations. Narrative amendments retain
the allocation; prior runs remain frozen after conduct corrections.

## Scoped validation

Commands use `services/science/.venv/Scripts/python.exe scripts/scoped_tests.py`
from `services/science`, with these arguments:

| Arguments | Result | Sampled scratch peak |
| --- | --- | --- |
| `tests/test_randomized_onset.py -q` | 17 passed | 2,423,725 bytes |
| `tests/test_native_randomized_onset.py tests/test_native_experiments.py tests/test_experiment_reports.py tests/test_native_report_history.py -q` | 9 passed | 8,875,587 bytes |
| `tests/test_native_report_history.py -q` after prioritizing reports | 1 passed | 2,049,771 bytes |

The first native pass had one failure in a new assertion that regenerated a timestamp;
corrected it to compare with the captured protocol timestamp. The complete scoped
native rerun then passed. Each runner enforced 512 MiB / 300 s and removed its own
verified scratch, including the failed pass. The history regression verifies preview,
byte-identical export, unchanged report versions and unchanged active data revision.
Qt regressions also check frozen fields, editable narrative fields, expandable visit
entry, unsupported method disabling, allocation preservation and figure semantics.

Owner manifest SHA-256 remained
`835398DA594421BC9F04647992B0E9CEFD5DC844FD931D1964896B2E164A2587`, unstaged.
No operational dataset, abandoned demo root or owner data was cleaned or rewritten.
No full-suite, installer, packaging, CI-policy change, publication, push, merge or release
campaign was performed. Scientific validity still depends on faithful prospective
randomization and the stated assumptions; these synthetic checks do not establish
real-athlete efficacy.
