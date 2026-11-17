# RES-717 E5 — Series of individualized experiments

Implemented in the existing persistent PySide6 workbench on 2026-11-17.

## Native workflow

Open a persistent workspace, choose **Research Workbench → Series of experiments**,
and Ctrl/Shift-select experiments belonging to distinct athletes. The roster lists
each individual investigation, latest experimental protocol, design, outcome/unit,
recorded versus scheduled observations, eligibility and latest saved result. More
than one investigation can exist for an athlete; a comparison requires distinct
athletes. Investigations without experimental protocols remain visible.

Selection previews explicit design checks and side-by-side participant panels.
Each panel keeps its own protocol, phase bounds, allocation, units, actual occasion,
visit timestamp, condition, exposure, missing reason and measurement. Missing values
break plot lines; separate axes are explicitly labeled. Planned onset markers are
distinct from actual conduct. Full visit ledgers, corrections, adherence and QC are
retained in the captured timeline. Open the complete participant experiment to
inspect or continue its native workflow; captured results and diagnostics and linked
historical reports are directly accessible from comparison panels.

**Save selected comparison** creates a new comparison record; use the frozen-history
selector to reopen it. Refresh the roster after conduct or protocol changes.

## Scientific contract

The series adds no estimator. It reuses RES-716 method contracts, the existing exact
randomized-onset evaluator, per-athlete analysis runs and frozen report versions.
Eligibility is assessed independently for each experiment. Matching definitions
are conservative checks, not proof of exchangeability or a shared causal effect.
No pooled treatment effect, combined p-value, imputation, unit conversion, temporal
alignment or speculative model is computed.

Checks separately expose:

- Outcome identifiers and labels; recorded units.
- Period structure: design, axis and relative scheduled occasions; elapsed scheduled
  calendar times and persistence/lag for randomized onset; phase kinds, labels,
  lengths and notes for crossover designs.
- Allocation mechanism and support relative to the participant's schedule origin,
  fixed statistic and alternative; documented assignment for nonrandom designs.
- Baseline/intervention definitions or documented phase labels/notes.
- Captured catalogue/method versions and latest saved analysis method/version.
- Complete scheduled observations and contextual issues.
- Latest result binding to investigation version, data revision and current method.

Different realized randomized starts do not themselves make experiments incompatible.
Their individual timelines remain separate. Check statuses are MATCH,
REVIEW_REQUIRED, COMPLETE, INSUFFICIENT, CURRENT or STALE_OR_ABSENT. Incompatible or
incomplete experiments can still be inspected and frozen with their warnings.
Missing experimental protocols cannot pass definition checks. Nonrandom crossover
results remain descriptive; they do not acquire randomized-onset inference.

## Persistence and reproducibility

Comparisons use an EXPERIMENT_SERIES scope in the existing versioned investigation
store. No new database schema or external application is required. Capture runs in
one transaction and rejects stale investigation/data-revision bindings, foreign
investigations, duplicate athletes and archived workspaces. Each new comparison has
its own ID and timestamp rather than replacing an older record.

The initial immutable investigation-version document holds canonical JSON with the
captured protocol, timeline, measurements, visit provenance, complete saved run,
diagnostics, result digest, reproducibility key, method contracts, report-version
references, checks and interpretation. Its SHA-256 is verified on historical read.
History reads the original version, rather than rebuilding from current observations
or amendments. Historical reports use the existing frozen renderer and do not
change the active revision or generate new analyses. Background UI callbacks reject
obsolete workspace generations; switching workspaces clears participant content.

## Validation

Commands ran from `services/science` using
`.venv/Scripts/python.exe scripts/scoped_tests.py`:

| Scoped arguments | Result | Sampled peak scratch |
| --- | --- | --- |
| `tests/test_experiment_series.py tests/test_experiments.py tests/test_randomized_onset.py -q` (first commit) | 23 passed | 6,581,154 bytes |
| `tests/test_native_experiment_series.py tests/test_native_report_history.py tests/test_native_experiments.py -q` | 6 passed | 5,863,005 bytes |
| `tests/test_experiment_series.py tests/test_native_experiment_series.py tests/test_native_report_history.py tests/test_native_experiments.py tests/test_native_randomized_onset.py tests/test_native_method_suite.py tests/test_experiment_reports.py -q` | 17 passed | 17,270,615 bytes |
| `tests/test_experiment_series.py tests/test_native_experiment_series.py -q` after adding calendar-spacing checks | 6 passed | 8,084,492 bytes |
| `tests/test_native_experiment_series.py -q` including the final check-definition dialog | 3 passed | 3,455,170 bytes |

Coverage includes independently expected synthetic athlete measurements and exact
individual p-values (1/26 and 1), persisted mixed randomized/nonrandom designs,
all definition mismatch categories, missing/planned observations, recorded missing
reasons, stale protocol/data bindings, duplicate/foreign selection rejection,
two-athlete isolation, unchanged historical comparisons after amendments/new data,
unchanged frozen HTML, native history reopening, report preview, captured diagnostics,
participant navigation, missing plot gaps and obsolete callback rejection.

Initial new-test failures identified an invalid amendment fixture, tuple/list JSON
round-trip inequality and an assumption about Qt child ordering. These were corrected
before the passing scoped runs. The native navigation assertion now selects by the
captured investigation ID.

Each runner enforced 512 MiB / 300 seconds and removed its own verified scratch on
success and failure. An additional isolated offscreen render was visually inspected;
its temporary synthetic workspace was removed and its screenshot retained outside
the repository at `D:/SWE_HOME/codex_home/artifacts/res717-series-20261117.png`.
The render explicitly loaded the installed Segoe UI font because the offscreen Qt
platform did not discover Windows fonts automatically.

The owner's pre-existing modified `data/synthetic/generator_manifest.json` remains
unstaged with SHA-256
`835398DA594421BC9F04647992B0E9CEFD5DC844FD931D1964896B2E164A2587`.
No operational research dataset was modified. No full-suite qualification,
packaging, live empirical efficacy validation, push, merge or release was performed.
