# RES-644 / RES-647 independent repair and qualification — 2026-11-12

Scientific application source: `e748962a8a0c3fc264959549cb10dc967e779c25`. RES-644 branch: `2bdf638305e62137b10fc42520de5701b2c90495`. Application Git tree: `47e9b7f82fde12395207f5dee0ce89da7c0b3b74`. The delivery evidence commit adds documentation and receipts; it does not change this qualified application source.

PR #3 remains based on main. PR #4 remains a draft stacked on the RES-644 branch. No merge, force push, reset, history rewrite, installed-app replacement or operational scientific-content write was performed. SQLite read-only source-copy tests refreshed the SHM file timestamp; its bytes remain unchanged (see preservation receipt).

## Engineering and scientific disposition

| Gate | Independent disposition and evidence |
| --- | --- |
| 0 — repository | Original PR #3 contained the documented eight RES-644 commits above remote main `2e9f53c`; original PR #4 contained the documented eight RES-647 commits above `5eefae4`. Repair commits remain on the corresponding existing branches. The original checkout's only unrelated change was the owner manifest, preserved byte-for-byte. |
| 1 — RES-644 | Confirmed and repaired unreferenced derived directories after handled append failures. Parquet-write and transaction-failure injection preserve existing revisions and support retry. Real v1-schema migration recreates the absent v2 table additively; injected DDL failure rolls back schema and version. Full RES-644 regression: 292 passes; two additional real-v1 migration checks pass. The final RES-647 full suite also exercises all inherited tests. See [RES-644 review](res644-review.md). |
| 2 — scenarios | Numerical Squad projections and projected flag crossings removed. Both paths save versioned HYPOTHETICAL definitions, `NOT_QUALIFIED`, and no numerical forecast. Favorable/reference/adverse labels describe assumptions. Legacy stored projection summaries remain historical documents and are no longer presented as future athlete conclusions. No arithmetic sandbox or forecasting model is shipped. |
| 3 — flags | Researcher-defined descriptive rules retain metric/unit, statistic unit, source/snapshot/revision, exact unrounded value, observations, threshold/operator, rule version, timestamp, missing occasions and QC eligibility. Finite eligible observations only; unavailable evaluations remain NOT_EVALUABLE. Saved rule evaluations retain their original versions. Events explicitly distinguish recorded evaluations from retrospective current-rule history. |
| 4–5 — native product | Research Workbench is a primary action. Squad has participant search, workspace/revision context and research navigation. Athlete pages separate measurements, rule evaluations and investigations. Active pages determine layout height; long specification forms scroll locally. Primary toolbar controls remain visible; keyboard shortcuts and focus support are present. Comparison columns fit without horizontal overflow; interpretation/limitations have an explicit action. Trajectory clipping is checked against ancestor viewports. Real work areas: 1366×720, 1093×576, 911×480 logical pixels. No global font or UI scale reduction was introduced. |
| 6 — ingestion | CMJ and monitoring retain distinct tables, metrics and captured source/rights/checksum records. Append compatibility, overlap rejection, participant confirmation and roster conflicts remain enforced. Mixed files have explicit family selection in Edit mapping, allowing separate imports and linking; repeated trials are not silently averaged into monitoring records. Multiple monitoring axes require one explicit date/day/week choice. Ordinary one-click imports remain intact. |
| 7 — individual arithmetic | Independent pairwise-difference SSE and standard-library calculations verify session means, sample SD, pooled within-session SD, first-to-last change and trial-noise SE. Cases cover unequal trials, single-trial endpoints, heteroscedastic sessions, no repeated trials, missing occasions and QC/nonfinite exclusions. Common-variance/independence assumptions and biological-variation exclusions are explicit. This is descriptive arithmetic, not causal response or total longitudinal uncertainty. |
| 8 — persistence and reports | Separate participants and investigations share one workspace. New revisions do not rewrite earlier runs; cohort selection remains separate. Runs capture investigation versions; new report sections use execution-time context. Old frozen reports remain immutable. Cross-participant and cross-revision completions are guarded. Portable receipt comparisons confirm identical report versions and run identities through internal and fully external restarts. |
| 9 — current walkthrough | Updated `scripts/res647_walkthrough.py` drives Squad/athlete/investigation, imports, cohort/individual analyses, protocol, hypothetical scenario, Events, comparison, exports, History and restart through Open workspace. Assertions cover state, identity, numerical eligibility, immutable earlier results, report sections, primary-action visibility and comparison viewport/overflow. `res647_scaling.py` verifies the current editors, trajectory visibility and screenshot hashes. |
| 10 — portable | Clean PyInstaller build, 54 embedded Python modules plus the entry point compared against compiled source. Native packaged workflows pass at all three scales, with five saved runs, two revisions, two participant investigations and three reports per workflow. Each first process exits before a separate external restart. Ordinary GUI entry/startup also passes with isolated settings. |
| 11 — regression/CI | **314 passed, 0 failed, 0 skipped in 396.75 seconds** on the exact source above. [Full log](res647/final-regression.log) and [receipt](res647/final-regression-receipt.json). Existing R-reference/scientific comparisons are retained. Windows PR CI now generates disposable fixtures, compiles Python, checks changed-source whitespace and runs unit/integration/migration/Qt/scientific tests, preserving JUnit results. CI does not constitute independent methodological validation. |
| 12 — delivery | Independently validated RES-644 commits were pushed normally. RES-647 repairs and evidence are delivered to the existing feature branch, with PR #4 kept draft. Full commit list below. |

## Scientific contract and numerical evidence

Observed measurements, descriptive/statistical results and hypothetical definitions are separate objects. No model passed RES-619/RES-590 forecasting gates during this work, and no numerical forecast is available. Scenarios cannot update observed athlete state, invent probabilities or generate injury/physiological conclusions.

The record ratio is the mean of the last A valid session records divided by the mean of the last C valid session records, with the short window included in the long window. It is not calendar ACWR. Incomplete windows and a zero denominator are unavailable; irregular measurements do not become seven/twenty-eight-day workloads. Missingness is relative to measured occasions in the revision, rather than an inferred calendar schedule. User thresholds have no asserted scientific risk validity.

For the individual descriptive method, pooled SD is `sqrt(sum((n_s-1)*SD_s²) / sum(n_s-1))`; change trial-noise SE is `pooled_SD * sqrt(1/n_first + 1/n_last)`. Pooling assumes independent, exchangeable trials and common within-session variance. Single-trial endpoints borrow the pooled noise estimate. Heteroscedasticity is not modeled. No repeats means no noise estimate. Neither this SE nor a cohort confidence interval is an individual response threshold or a predictive interval. Observational protocols and documented N-of-1 designs remain distinct; the shipped descriptive method makes no causal inference.

- [Independent edge-case receipt](res647/independent-numerical.json).
- [Independent portable results](res647/portable-independent-numerical.json): **15 runs, 63 session/cohort points and nine trial-noise estimates** checked from saved packaged results using independent standard-library calculations.
- [Portable numerical verifier](res647/verify-portable-numerical.py).
- [Portable persistence receipt](res647/portable-persistence.json) and [external process restarts](res647/portable-process-restarts.json).

## Native and packaged evidence

| Scale | Source workflow | Screen/editor checks | Portable workflow | Fully external restart |
| --- | --- | --- | --- | --- |
| 100% | [Receipt](res647/delivery-source-100/receipt.json) | [Receipt](res647/delivery-screens-100/scaling-receipt.json) | [Receipt](res647/portable-100/receipt.json) | [Receipt](res647/portable-external-restart-100/reopen-receipt.json) |
| 125% | [Receipt](res647/delivery-source-125/receipt.json) | [Receipt](res647/delivery-screens-125/scaling-receipt.json) | [Receipt](res647/portable-125/receipt.json) | [Receipt](res647/portable-external-restart-125/reopen-receipt.json) |
| 150% | [Receipt](res647/delivery-source-150/receipt.json) | [Receipt](res647/delivery-screens-150/scaling-receipt.json) | [Receipt](res647/portable-150/receipt.json) | [Receipt](res647/portable-external-restart-150/reopen-receipt.json) |

Representative current screenshots: [150% athlete trajectory](res647/delivery-screens-150/01b-athlete-trajectory.png), [150% comparison](res647/delivery-source-150/09-compare-with-cohort.png), [150% flag editor](res647/delivery-screens-150/04-flag-rules.png), [hypothetical definitions only](res647/delivery-screens-150/05-simulation.png), [packaged individual results](res647/portable-150/04-individual-results.png). Each receipt records screenshot hashes.

Portable EXE SHA-256: **`e43bb87faa0f0b70c5bee3b7461172cfe1c6fd4ecdfc58a05d066105ff7db9ce`**, 31,537,702 bytes. It remains in the isolated `C:/Users/Usuario/AppData/Local/Temp/dynamis-independent-20261112/delivery-dist/DynamisScience/` folder with its required `_internal` directory. [Build receipt](res647/build-receipt.json), [embedded-code identity proof](res647/package-identity.json), [identity verifier](res647/verify-delivery-package.py), [build log](res647/delivery-build.log), [external process driver](res647/portable-qualification.ps1).

## Preservation, limits and severity

- **No remaining forecast authorization:** RES-619/RES-590 are still required for any numerical predictive model. The current disabled forecast path is intentional scientific scope, not a forecast qualification claim.
- **Low — abrupt termination:** handled failures clean up their own uncommitted derived directory. OS termination or power loss can still leave an unreferenced directory, which never becomes an admitted/selected revision. Automatic sweeping could race another materializing process; a separately designed maintenance operation is preferable.
- **Low — ambiguous mixed ingestion:** there is no automatic aggregation of repeated CMJ rows into monitoring. Researchers explicitly choose family/time mapping and import/link separately. This preserves source meaning and sampling rather than inventing correspondences.
- **Scope — individual methods:** the individual statistical method remains a descriptive CMJ trajectory. Linked monitoring remains available as separate observed data and rule inputs; no newly qualified monitoring/causal/forecast method is implied.
- **Legacy context:** earlier individual runs without a recorded investigation version cannot recover execution-time protocol metadata retrospectively. New report metadata marks their export-time context as legacy; immutable previously frozen reports are retained. New runs capture the exact version.
- **Qualification execution:** the concurrent full run had 312 passes and two legacy Qt failures: the existing five-second monitoring-form wait expired, followed by a late signal against a deleted test QObject. Both tests passed in isolation. The final complete suite was rerun without simultaneous native/build work, with no timeout or numerical tolerance changes. The failed run is retained as [concurrent-run evidence](res647/concurrent-regression-failed.log).
- **Build warnings:** optional Jupyter/legacy GLUT dependencies are reported in the build log. The requested native two-dimensional scientific workflows were exercised; no additional optional Jupyter or legacy GLUT capability is claimed.
- **Owner-controlled actions:** both PRs remain unmerged and PR #4 remains draft. No installed-product replacement, release publication or owner scientific/design acceptance is inferred from these receipts.

## Atomic repair and integration commits

```text
e748962a8a0c3fc264959549cb10dc967e779c25 RES-647 Fit active scientific pages and comparison tables to native work areas
983fa37e70f2df9e12d049a91a40f34e63567c62 RES-647 Guard comparison revisions and require unambiguous monitoring time axes
092b1250d72b5e40742b427bec0ab10d734396aa RES-647 Keep scenario actions visible and qualify high-DPI editors
960959f87b7cd1e66a0e93a927bc291de222f7bf RES-647 Integrate independent legacy migration verification
97cd6ff77b6a5527f2eb2628178aeb286b2f1307 RES-647 Freeze investigation versions and preserve linked measurement sources
2bdf638305e62137b10fc42520de5701b2c90495 RES-644 Verify additive v1 migration and transactional DDL recovery
c933a6c8f29276a37407e34bb6a92589bc13ee7a RES-647 Add repeatable Windows regression and packaged qualification entry
2a41945c5f40febf18e7c113371bf06dcd600b92 RES-647 Integrate independently qualified RES-644 append recovery
695d8d62083d56ffe47f740922b137a88faaeecf RES-647 Exercise current native research workflow and correct work-area overflow
2bfa41ef82b7460a7f0133df942d537047a8d85b RES-644 Roll back uncommitted derived data after failed append
f660ae7f1efde96accfd6eafa384cc4954064322 RES-647 Provide explicit mixed-family import recovery without pooling
cc931135308022343003f72cf6de577c7ab046d5 RES-647 Make research navigation and athlete investigations accessible at high DPI
5b9998c2e817e8c9034bc5a2d71ae7f9ec190470 RES-647 Qualify individual trial-noise arithmetic and state variance assumptions
d116fb5627bcc8dfbfe3b03a577c0dda80f8ebc6 RES-647 Record descriptive flag provenance and distinguish retrospective evaluations
87b3f9cc5f85cdd8a79ba7f3330f1a0af2ddca75 RES-647 Preserve hypothetical definitions and disable unqualified numerical futures
b97babba7092471a6c99f29b6fac1c0f1bafb3da RES-647 Qualify Squad, athlete, Events and editors at 125% and 150%
974f505fcf7ebc69f40b178194107c3fd7854471 RES-647 Events feed: flag changes, new data, analyses and follow-ups
352e5e89b7fda9224be5520762292a6357939aba RES-647 Import athlete monitoring and link it to CMJ in one revision
08da414636893fc0f106940f9fcfca8e5d59adb9 RES-647 Squad home perspective with athlete pages, branches and simulations
f6a7594ccbc50119ac1c7ee7a2a0a62d75beace0 RES-647 Add researcher-configured squad flag rules and simulations
7dc0ae8cdfc1eff935c5f718795de8d0fcadbe92 RES-647 Record native longitudinal research qualification
d6a00f0f9451abe15525af89ab2d5a4c58bf21dd RES-647 Native individual research context, explorer and research panel
d0d62378f0b5983097271ce3e5fea2886d4d536c RES-647 Add individual research scopes, protocols, scenarios and labeled reports
```

The owner manifest remains uncommitted, SHA-256 `835398DA594421BC9F04647992B0E9CEFD5DC844FD931D1964896B2E164A2587`. The operational research database remains checksum-identical to its original `93ebb1eea705ac879f02dab56b499397780acc75e8ab45fe39c06aaa21f35eaea`. Final preservation and regression receipts accompany the evidence.

Preservation detail: [inventory and checksum receipt](res647/data-preservation.json) records 1,930 operational files before/after with identical counts, sizes and modification times except for the SQLite SHM timestamp. The DB, WAL and SHM hashes are each unchanged. No timestamp restoration or operational-file rewrite was attempted.
