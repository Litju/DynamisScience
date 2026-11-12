# RES-647 — Cohort & Individual Longitudinal Research

Branch `codex/res-647-longitudinal-research`, based on RES-644 `5eefae4`. No push, PR, merge or installer execution was performed.

## Contracts

- **One workspace.** Individual research is a scope of the existing persistent workspace (`STUDY-U-*`). No second project, application, database or ETL path was added. Schema version is unchanged (2); no table was added.
- **Research scope.** Runs record `scope` (`COHORT`, or `INDIVIDUAL` + `subject_id` + `investigation_id`). An individual scope is a frozen cohort with exactly one included participant over the same admitted revision; no source data is copied per participant.
- **Individual investigations** are versioned rows of the existing `investigations` / `investigation_versions` tables with an `INDIVIDUAL` scope, a question, a protocol and scenarios. Every protocol/scenario save appends an investigation version; earlier versions remain readable.
- **Individual analysis.** `METH-U-INDIVIDUAL` 1.0.0 (QUALIFIED_DESCRIPTIVE): observed session means, within-session trial SD, pooled within-session SD (df reported), first-to-last change and its trial-noise SE = pooled SD × √(1/n_first + 1/n_last). It requires ≥2 measured occasions for the participant, lists missing occasions and is explicitly not a causal estimate or forecast. Cohort methods are ineligible in individual scope and vice versa, each with a stated reason. Existing numerical routines and thresholds are unchanged.
- **Individual runs never replace the workspace cohort selection** (cohort/plan binding and selected cohort run are preserved).
- **Experimental protocol.** Periods (baseline, intervention, exposure, comparison, washout, follow-up), testing occasions, protocol changes, adherence and deviations. Overlapping periods are rejected. `N_OF_1_EXPERIMENT` requires ≥2 intervention and ≥2 comparison/baseline periods, a documented assignment and prespecification; otherwise the record stays "Retrospective observational tracking — not an experiment".
- **Scenarios** are always `HYPOTHETICAL`, with the referenced revision/model run, outcome, canonical unit (mismatches rejected), parameter bounds, horizon, adverse-outcome definition (required for worst case) and assumptions. No forecasting model is qualified (RES-590/RES-619), so every scenario records `NOT QUALIFIED — Numerical forecast unavailable.` and `numerical_result: null`.
- **Compare with cohort** shows individual observed session means and trial SD next to descriptive summaries of the other participants on the same revision/metric/unit/axis, separately lists qualified cohort-level model runs and hypothetical scenarios, and states that population statistics are not individual forecasts.
- **Reports.** Export accepts one or several runs. Each run is cited under a labeled section (`Cohort research` / `Individual investigation · participant … · title`). The frozen version captures `research_sections`, including the investigation version, protocol and scenarios. Reports frozen before RES-647 render unchanged.
- **State.** The workspace persists `research_context` (scope, participant, investigation). The UI restores it on reopen; panel loads and analysis completions are discarded if the workspace, investigation or revision changed; switching participant clears the previous participant's tables immediately.

## Commits

- `d0d6237` — backend contracts: scopes, individual investigations, `METH-U-INDIVIDUAL`, protocol, scenarios, cohort comparison, labeled report sections.
- `d6a00f0` — native context bar, Individuals explorer, Individual Research tab, scope-aware export/combined report/history; deterministic 12-participant study tests.
- Evidence commit — walkthrough frame sizing fix, receipts, screenshots and this record.

## Verification

- **Full Qt/scientific regression at `d6a00f0` (offscreen): 294 passed, 0 failed** — 290 existing plus 4 RES-647 tests ([log](res647-evidence/full-regression.log)). One existing assertion changed intentionally: the research workbench now has six tabs (five workspaces plus Individual Research).
- RES-647 tests use a deterministic study: 12 pseudonymous participants, six weekly occasions, 2–3 repeated trials, missing follow-ups (P03, P07, P11) and two revisions (weeks 1–3, compatible append of weeks 4–6). They cover all 14 acceptance steps, an independent NumPy recomputation of the individual method, protocol/scenario validation and history, stale/cross-participant completion guards and reopen recovery.
- **Source-native Windows Qt journey** (`scripts/res647_walkthrough.py`, real `windows` platform, real import dialog and native input dialogs): [100% light](res647-evidence/source-100/receipt.json) (1366×720 work area of a 1366×768 desktop), [125% dark](res647-evidence/source-125/receipt.json) (1093×576), [150% dark](res647-evidence/source-150/receipt.json) (911×480). Each creates one workspace, imports two ETL batches, runs cohort analysis, opens Participants A and B through the explorer, analyses both, appends follow-up data, re-analyses A on revision 2 (A's revision-1 run byte-identical), saves a protocol and a worst-case scenario (NOT QUALIFIED), compares with the cohort, exports individual, cohort and combined reports, inspects History, restarts in-process and then **in a separate process** (`reopen-receipt.json`, distinct PID) that restores the individual context, both runs and all report versions. Zero application warnings were recorded.

## Known limits

- At 150% the scope/investigation pickers, Individuals and Combined report move into the toolbar overflow (`»`); at 100% only Combined report does. All remain reachable; the Individual Research content scrolls within Results.
- No portable PyInstaller package was rebuilt or qualified for RES-647; installed-app acceptance remains open.
- Individual compare and protocol-period observations are computed from the active revision when viewed; they are not stored as evidence.
- No hierarchical, Bayesian, state-space or mechanistic individual model was added; scenarios cannot produce numbers until one passes RES-590/RES-619 qualification.

The owner's `data/synthetic/generator_manifest.json` modification remains uncommitted and untouched. All walkthrough data roots were disposable temporary directories; the operational research database was not opened.
