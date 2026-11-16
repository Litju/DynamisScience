# RES-716 — Scientific Methods Suite, first native slice

Implemented 2026-11-16 in the existing Python/PySide6 workstation. This is feature development, not release qualification.

## Researcher workflow

1. Open a research workspace with admitted data and choose **Analyze**. The cohort selector lists eligible methods first and retains scientifically ineligible, rejected and unavailable entries for inspection.
2. Choose the outcome and inspect the method contract: identity/version, estimand, designs, population/data requirements, units, timebase, assumptions, missingness, uncertainty, diagnostics, outputs, evidence and limitations. Run is disabled for an ineligible selection. Parameters are checked again at execution.
3. Run an eligible descriptive, MixedLM or repeated-trial reliability method. Existing estimators are reused. Cohort results show recorded estimates/intervals and diagnostics, with the captured execution contract.
4. Open a participant investigation and its **Analysis** tab. The same catalogue explains why cohort inference, experimental effects and forecasts cannot run for that participant. The existing individual trajectory method computes session means and observed change with trial-noise context. Results and history retain their data revision.

## Implementation and scientific bounds

- `services/science/dynamis_science/method_catalogue.py`: catalogue 1.0.0, derived from the existing method specifications and RES-619 matrix. Synthetic arm/time and baseline reliability are explicitly restricted to their reference workflow. Experimental effects, forecasting and rejected body-weight recovery have explicit unavailable states; the fitness–fatigue prototype is exploratory.
- `researchstore.method_eligibility`: shared planning checks on the selected metric, design, population and actual rows. Rejects unsupported tables/scopes/designs, missing units, invalid parameters, non-finite outcomes, invalid time/trial metadata, duplicate MixedLM athlete/occasion rows, insufficient observations and inappropriate reliability metrics. Outcome missingness is counted, never imputed.
- `desktop.services.analysis_methods`: read-only planning; saved cohort rules and explicit exclusions are respected. Workspace previews are revision-pinned. Both scientific execution paths enforce eligibility independently of the UI.
- New runs capture a detached method specification, catalogue/method versions, effective parameters, registered outcome/units, snapshot/checksums, data revision, included/excluded participants, Git HEAD and a SHA-256 of the scientific implementation sources. The binding participates in the reproducibility key. Historical runs are not rewritten; existing RES-619 supersession rules remain authoritative.
- The ribbon's existing engine specifications now include method version in their identity/payload and reject unsupported role mappings or a requested interval other than the existing fixed 95% interval.

Numerical qualification remains limited to the evidence recorded by RES-619/647. No new estimator, causal individual effect or forecasting claim was introduced. The existing MixedLM optimizer/fallback behavior remains; a synthetic execution took roughly 98 seconds, so this work makes no latency claim. Live row-exploration tools remain separate from persisted scientific suite runs.

## Executable validation

Run from the repository root with the existing environment:

```powershell
services/science/.venv/Scripts/python.exe services/science/scripts/scoped_tests.py tests/test_native_method_suite.py tests/test_method_catalogue.py tests/test_longitudinal_research.py tests/test_workbench_spec.py tests/test_science.py::test_two_way_icc_reproduces_shrout_fleiss_1979_table tests/test_science.py::test_descriptive_mean_interval_uses_student_t tests/test_science.py::test_descriptive_interval_unit_is_the_athlete
```

- Main science/Qt run: **50 passed in 118.52 seconds**. Sampled scratch peak **3,019,267 bytes**, exit 0, scratch removed.
- Final native/spec follow-up after adding stale-preview invalidation and saved-cohort preview checks: **20 passed in 9.08 seconds**. Sampled scratch peak **690,930 bytes**, exit 0, scratch removed. These overlap the main run.
- First backend commit validation: **23 passed in 40.04 seconds** (catalogue plus existing longitudinal tests); final backend-only check **12 passed in 4.05 seconds**.

The native test creates/imports deterministic synthetic longitudinal data, opens the actual MainWindow, rejects unsupported MixedLM/forecast selections, executes a 12-athlete descriptive analysis, creates a participant investigation, executes its trajectory (independently calculated change **0.9 cm**), inspects saved provenance and rejects a cohort method in individual scope. It also checks invalid parameter editing cannot re-enable an old selection, planning does not mutate the study, stale revisions fail, and saved cohort restrictions are respected.

The engine regression executes the existing MixedLM and ICC paths on synthetic rows. The balanced-design slope is compared with a separate OLS calculation; ICC and TE match the existing independent ANOVA reference to relative tolerance 1e-12; MDC95 matches the exact normal quantile calculation. Negative cases include non-finite outcomes, invalid ordinal values, duplicates, inadequate sample size, wrong scope/design, absent contrast occasions and unsupported alpha/metric choices. Two initial test expectations were corrected: synthetic session variation makes the individual change 0.9 rather than 0.8 cm, and the engine uses the exact normal quantile rather than rounded 1.96.

`scoped_tests.py` enforces a 512 MiB sampled scratch budget and 300-second timeout, kills the child process tree if necessary, and removes only its verified temporary directory in `finally`, including failed runs. Qt tests use the offscreen platform; no physical-display, installer, packaging, R qualification or release campaign was run.

## Protection and commits

- Initial HEAD: `7761fdc`; all earlier commits retained, current checkout reused.
- Backend commit: `8ccb06d` — `RES-716 Add versioned scientific contracts and execution eligibility`.
- Native selector/results and follow-up validation are the second RES-716 commit; its exact SHA is reported in the delivery message.
- No test source was copied from or run against `D:\datasets\DynamisScience`; tests use synthetic inputs and isolated data roots.
- Owner-modified `data/synthetic/generator_manifest.json` was neither regenerated nor staged. Its SHA-256 remained `835398DA594421BC9F04647992B0E9CEFD5DC844FD931D1964896B2E164A2587`.
- No push, merge, reset, history rewrite or worktree migration.
