# RES-619 — Statistical methodology and evidence-validity audit

Audit date: 2026-11-10. Baseline: `e875427` (RES-613). Scope: the existing methods only. New Bayesian, ML and PIML families remain RES-590.

All numbers below come from isolated copies of the admitted snapshots or from pytest's isolated data roots. The private research root `D:\datasets\DynamisScience` was read, never written.

## Method matrix

| Method (catalogue id, version) | Estimand | Eligibility / missingness | Key assumptions | Diagnostics | Evidence class | Main limitations | Code |
|---|---|---|---|---|---|---|---|
| Linear mixed-effects change (`METH-REAL-TREND` 1.1.0) | Population mean within-athlete CMJ-height change per occasion (fixed slope), and model-implied change between two occasions | ≥3 subjects, ≥8 complete rows. Complete case at the outcome, no imputation (MAR assumed) | Linear in occasion. Random intercept + slope per athlete. Normal, homoscedastic within-athlete errors. Occasions are ordinal, not equally spaced time | Optimizer attempts and selection by log-likelihood, convergence, marginal residuals by occasion, **σ̂-scaled conditional residual Q–Q** (nlme `pearson` convention; lme4 2.1 `type = "pearson"` is unscaled), sample context | **Qualified** against R lme4 (ML), end to end from `DATA.xlsx` | Single cohort (21 athletes, 4 occasions). ML Wald z interval for the slope [0.622, 1.375] is narrower than profile [0.609, 1.400] and t(20) [0.599, 1.398]; no Satterthwaite/Kenward–Roger correction. BLUP intercepts are non-normal (Shapiro p = 0.003). Random-intercept fallback changes the estimand's SE basis. Effect size divides by baseline SD and falls back silently to pooled SD | `realanalysis.py:655` (`_fit_trend`), `qualification_real.py:53` |
| Synthetic longitudinal arm × time (`METH-LONG`) | Difference in change between arms | First valid trial per athlete-week | As above, plus arm-specific slopes | As above. Q–Q from `_normal_qq` (z-scored) | **Qualified, synthetic only** (cluster-robust OLS reference for fixed effects) | No external validity. Fallback chain changes the estimator class | `analysis.py:43`, `analysis.py:89`, `analysis.py:289` |
| Repeated-trial reliability (`METH-REAL-RELIABILITY` 1.1.0, synthetic `METH-REL`) | ICC(3,1): consistency of a single trial, trials as a fixed factor. Typical error = √MSE. 95% MDC = 1.96·√2·TE | ≥3 subjects with ≥2 trials. Only force trials with a matching IMU recording (snapshot eligibility). Balanced on the first *k* trials **in acquisition order** (timestamps agree with trial numbers). Extra trials are excluded and counted | Two-way ANOVA, subjects random. No subject × trial interaction. Normal errors for the F-based CI | Balanced design, trials used/excluded, Shrout–Fleiss F CI on MSR/MSE, ICC(1,1) and ICC(2,1) sensitivities, per-subject CV | **Qualified** against statsmodels OLS ANOVA and an R pipeline from the raw force CSVs | Within-session consistency of peak vertical GRF, not between-day reliability or device agreement. Contributing force plates vary within MS-03, MS-04, MS-07. Peak force not normalised to body weight. Walking speed uncontrolled | `analysis.py:367` (`two_way_icc`), `realanalysis.py:628`, `realanalysis.py:992`, `qualification.py:18` |
| Descriptive occasion / activity means (`METH-REAL-DESC` 1.1.0, `METH-U-DESC` 1.1.0) | Mean of athlete values, SD and Student-t 95% CI per occasion or activity; **the athlete is the unit** (repeated trials averaged within athlete first) | Observed values only; missing counted | Athletes independent within a point | Counts (athletes and trials), missingness | **Descriptive** | No inference across occasions; the per-point CI ignores correlation between points | `realanalysis.py:617` (`mean_ci_half_width`, `subject_means`), `realanalysis.py:886`, `researchanalysis.py:75` |
| Individual change (`METH-U-CHANGE`, synthetic `_individual_change`) | Per-athlete change between two observations; cohort change SD | Complete pairs only | Observations comparable | Pair counts, missing pairs | **Descriptive** | The "typical error" here is change SD/√2 across an intervening block. It includes true individual response, so it is not measurement error. `exceeds_typical_error` is context only | `researchanalysis.py:128`, `analysis.py:532` |
| Force-plate signal derivation (`METH-REAL-SIGNAL-QA`) | Summed Fz peak, support detection and impulse (trapezoid) at 1000 Hz | Matched trials; plates missing are flagged | Local Z axis is vertical. Baseline = median of the first 100 samples | Saturation, NaN counts, clock offsets | **Qualified** on 4 representative trials (independent NumPy re-derivation) | Not all 398 trials re-derived. No orientation calibration. **No sample-level IMU↔force synchronisation** (clocks differ by about 4 h). MoveSmart has **no CMJ trials**, so no cross-modality CMJ validity is inferred | `realanalysis.py:914`, `qualification_real.py:261` |
| Body-weight recovery from support force (`METH-REAL-BODYWEIGHT`) | Bias and limits of agreement against folder-name metadata | Walking / heel-drop windows | Metadata weight is a valid comparator (weak) | Bland–Altman plot | **Rejected / exploratory** (bias −169 N, −22.9%) | The comparator is not an independent scale measurement | `realanalysis.py:914` |
| Fitness–fatigue prototype (`simulate_training_response`, `_training_response`) | Two-exponential performance state from weekly load | Synthetic weekly load | Banister-type impulse–response; fixed gains | Grid-search fit RMSE, residuals | **Prototype / unavailable for evidence** | No uncertainty, no identifiability analysis, synthetic only. Not for athlete predictions | `analysis.py:565`, `analysis.py:586` |

## Verified corrections

| Commit | Defect demonstrated | Correction |
|---|---|---|
| `4b80ab3`, `bd12884` | "ICC(3,1)" was computed with the one-way within mean square, i.e. ICC(1,1). The real-data path also **sorted each participant's peak forces ascending** before trimming to *k*, so it kept the 5 smallest of 6–11 walking trials. The "independent" qualification reference duplicated both errors. `1.96·√2·TE` was labelled "smallest worthwhile change" | Shared `two_way_icc` (Shrout & Fleiss 1979; McGraw & Wong 1996). Trials kept in acquisition order. TE = √MSE (Hopkins 2000). Renamed to `minimal_detectable_change_95`. Reference replaced by statsmodels OLS two-way ANOVA. `bd12884` only restores LF line endings that `4b80ab3` converted to CRLF |
| `4b02cf8` | The MixedLM Q–Q plotted **marginal** residuals `y − Xβ̂` divided by the **conditional** σ̂. On Mendeley CMJ these have SD ≈ 4.88σ̂, because between-athlete variance dominates. The plot therefore could not assess the within-athlete normality assumption. Blom positions were off by one (`(j+0.375)/(n+0.25)` with 0-based *j*) | Q–Q uses conditional Pearson residuals `(y − Xβ̂ − Zb̂)/σ̂` with correct Blom positions and an N(0,1) line. Marginal residuals remain only for by-occasion mean misfit and are labelled. `residual_qq_type`/`residual_definitions` are recorded per run. Legacy runs render "residual type not recorded" |
| `64bfae9` | README and SYSTEM_DESIGN claimed MoveSmart is CC BY-NC-SA 4.0 / non-commercial. The admitted manifest and the publisher say CC0-1.0 | The documentation now points to the manifest. Code already reads the licence from the manifest (dataset labels, lineage, figure provenance, HTML report) |
| `db20af7` | Descriptive mean CIs used z = 1.96 with n = 9–21 per group | Student-t half-width with df = n − 1. Limits of agreement are unchanged |

## Independent comparisons

| Quantity | DynamisScience | Reference | Difference | Tolerance |
|---|---|---|---|---|
| Shrout & Fleiss (1979) Table 2: ICC(1,1) / ICC(2,1) / ICC(3,1) | 0.17 / 0.29 / 0.71 | Published 0.17 / 0.29 / 0.71 | Matches at 2 d.p. | 2 d.p. (published precision) |
| MoveSmart walking ICC(3,1), n = 9, k = 5 | 0.8887265872 | R 4.6.2 `aov(y ~ subject + trial)`: 0.888726587162 | < 1e-11 | statsmodels OLS reference: 1e-9 relative |
| Same: 95% CI | 0.745195378 – 0.969296540 | R: 0.745195377614 – 0.969296539958 | < 1e-9 | — |
| Same: typical error | 75.7826 N | R √MSE 75.782605988 N | < 1e-9 | 1e-9 relative |
| Superseded 1.0.0 values (same data) | ICC 0.9511 (0.880–0.987), TE 49.71 N | — | Reliability was overstated | — |
| Mendeley MixedLM log-likelihood | −208.311800311 | lme4 ML −208.311800312 | 1.6e-10 | 1e-3 |
| Fixed intercept / slope | 38.6501331 / 0.9984512 | lme4 38.6501328 / 0.9984516 | 2.5e-7 / 3.8e-7 | 1e-4 abs |
| Slope SE | 0.192008 | lme4 0.191613 | 0.21% relative | 0.5% relative |
| Conditional residuals (82) | statsmodels `resid` | lme4 `residuals(fit)` | max 2.5e-5 cm | 1e-4 cm |
| Conditional Pearson residual SD | 0.836σ̂ | Expected < 1 (BLUP shrinkage) | — | Test bound 0.5–1.0 |
| t(0.975, 20) | 2.085963 | Standard tables | < 1e-8 | 1e-8 relative |

The tolerances are the existing RES-587 tolerances. The residual tolerance matches the fixed-effect tolerance because both depend on the same optimizer convergence.

## Rights reconciliation (MoveSmart, `SRC-ZENODO-17376717`)

- Zenodo API `license.id = cc-zero`, version v1.0, published 2025-11-04 (re-fetched 2026-11-10).
- DataCite `rightsList`: `cc0-1.0` (SPDX) **and** "© 2025 The Authors", `rightsstatements.org/vocab/InC/1.0/`.
- The admitted `provenance_manifest.json` and `snapshot.json` record CC0-1.0 and `commercial_use: PERMITTED`. They were not modified.
- No publisher source supports CC BY-NC-SA. The coexisting In-Copyright statement is an **owner review item** before any commercial reliance. Privacy obligations (PSEUDONYMOUS, no folder names, no re-identification) apply regardless of licence.

## Remaining limitations and research-only areas

1. Historical runs keep their recorded values, by design, and are now flagged SUPERSEDED on read (see below). The operational private store has **not** been migrated or re-run: that needs explicit owner authorization. Its frozen report `STUDY-U-60C639BA` v2 cites superseded trend evidence `EVID-U-0001` and exports with a warning banner.
2. Mixed-model intervals are ML Wald z intervals with 21 athletes. A small-sample correction (Kenward–Roger via `pbkrtest`/`lmerTest`) was not implemented, because no independently qualified Python route exists here.
3. The conditional-residual Q–Q is exploratory: BLUP-based residuals are shrunk and correlated. No formal normality test or random-effect Q–Q is provided. No sensitivity analysis (e.g. robust or REML) is offered.
4. Individual-change "typical error" (change SD/√2 over an intervention block) is not measurement error. The key name is unchanged, to keep the contract stable. The real-data path labels it, but the synthetic path does not.
5. The synthetic generator catalogue (`generate.py`, METH-REL outputs) still names "smallest worthwhile change". It was not edited, to keep the generated `DS-SYNTH-001` manifest and the pre-existing `generator_manifest.json` change untouched.
6. Fitness–fatigue remains a prototype. Body-weight recovery remains rejected.
7. GUI evidence was captured with the real `MainWindow` on the offscreen platform (Windows fonts). It was not captured on a physical display; the installed-package smoke (below) checks values, not pixels.
8. No external practitioner or independent human statistical review has taken place (RES-589). This audit is an agent review, cross-checked only against R, statsmodels and the published tables above.
9. Whether ICC(3,1) (consistency) or ICC(2,1) (absolute agreement) is the right primary estimand, and whether mixed-plate trials should be excluded, are **human statistical judgements**; the data do not decide them (see below).

## Verification round 2 (2026-11-10)

### Additional defects found and corrected

| Commit | Defect | Correction |
|---|---|---|
| `4375a58` | Runs did not record the implementation version: the reference-study path wrote spec `method_version: "1.0.0"` unconditionally, so corrected and erroneous runs were indistinguishable. DESC methods were not bumped after the t-interval change. | Runs record `method_version`; `SUPERSEDED_METHOD_VERSIONS` + `method_status()` derive CURRENT/SUPERSEDED on read. Superseded runs cannot be promoted, newly cited or frozen into a new report version. Historical frozen reports still export, with a banner, a status column and `method_status` in the manifest. Figures from superseded runs carry a SUPERSEDED title. Qualification binds only to current runs and archives prior receipts. |
| `ddb44e0` | Activity and repeated-trial summaries pooled every trial as independent (walking n = 82 trials from 10 athletes; the metadata said "1.96 × SEM across trials"). | Athlete means first (`subject_means`); n = athletes. |
| `7f81862` | In the rendered PNGs: the authored trend panel was titled "Model-implied estimate" while plotting observed means; categorical participants and activities were joined by lines; axis labels showed raw metric ids; interval types were unnamed. | Titles and legends state what is plotted and which interval; categories are drawn as markers only. |
| `95a5f1e` | Qualification references reused rows already selected by the app. | R pipelines start from the raw sources; regression tests compare selection, df, mean squares, every ICC quantity and residuals. The residual definition now states the lme4 vs nlme `pearson` difference. |
| `78cf28d` | The installed smoke only compared packaged digests with digests from the same source. | Installed workers must reproduce the R reference values and method version 1.1.0. |
| `4c014d5` | Runs did not disclose IMU-match eligibility, excluded participants or mixed plate counts. | Computed per-run limitations; explicit within-session estimand. |

### Pipeline-level reliability validation (raw archive → ICC)

`scripts/real_reliability_pipeline.R` works from the raw archive as follows:
- reads all 83 raw walking force trials (every plate CSV);
- finds 82 with an IMU recording (`P1 walk0004` has force data only);
- sums plates, treating NaN as 0;
- orders trials by the force file `TIME_STAMP`;
- keeps participants with ≥ 2 trials (MS-06 has one);
- takes the first k = min(8, 5) = 5.

Results:
- Acquisition order equals trial-number order for every participant. R's selection equals the app's: MS-01 uses trials 1, 2, 3, 5, 6; MS-03 uses 1, 2, 3, 4, 6; MS-08 uses 12–16.
- All 82 raw-derived peaks equal the snapshot `fz_peak_n` (max |Δ| 2.3e-13 N).
- `aov(y ~ subject + trial)`: df 8 / 4 / 32. Mean squares: subject 235 086.19, trial 2 540.41, error 5 743.00; one-way MS within 5 387.16.
- ICC(3,1) 0.888726587162 (Shrout–Fleiss 0.745195–0.969297); ICC(1,1) 0.895042 (0.761746–0.970990); ICC(2,1) 0.894897; TE 75.782606 N; MDC95 210.054807 N.
- The app differs from R by ≤ 3e-15 relative (`res619-evidence/r-reliability-icc.csv`).

**Estimand judgement for a reviewer:** the trials are repeated walking passes in one session, not raters. The trial effect is small (p = 0.78), so consistency and agreement coincide here (0.889 vs 0.895). ICC(3,1) is defensible for "single-trial consistency within a session". ICC(2,1) is arguably the conventional test–retest choice (Koo & Li 2016). Neither supports between-day reproducibility, and the high ICC is partly driven by between-participant body-mass differences, because peaks are not normalised.

### MixedLM validation (raw source → lme4)

`scripts/real_mixedlm_pipeline.R` derives the 82 CMJ rows from a verbatim `DATA.xlsx` dump: post rows only, `CMJht` × 100. The rows are identical to the snapshot (max |Δ| 4e-14 cm). It fits `lmer(..., REML = FALSE)` with both bobyqa and Nelder–Mead, which give the same log-likelihood (−208.3118).

| Quantity | App | lme4 | Max difference |
|---|---|---|---|
| Fixed intercept / slope | 38.6501331 / 0.9984512 | 38.6501330 / 0.9984513 | 1.4e-7 |
| Slope SE | 0.192008 | 0.191613 | 0.21% (tolerance 0.5%) |
| Variance components, σ̂ | — | — | ≤ 6.9e-5 relative |
| BLUP intercepts / slopes (21) | statsmodels | `ranef` | 8.4e-6 / 6.2e-6 |
| Marginal / conditional fitted (82) | — | — | 3.2e-7 / 9.8e-6 |
| Q–Q theoretical (Blom) / observed (82) | — | — | 4.7e-15 / 4.9e-6 |

The app's optimizer selection is honest: L-BFGS and BFGS did not converge, and Nelder–Mead was selected. The fit is not singular (intercept–slope correlation −0.08). The σ̂-scaled conditional residuals have SD 0.836 because of shrinkage. They are not independent N(0,1), so the Q–Q stays exploratory. The residual Shapiro p = 0.78 is context only; the app does not test normality.

### Descriptive intervals

Occasion summaries (Mendeley) have exactly one row per athlete per occasion, so n already equals the number of athletes. Activity and repeated-trial summaries were corrected to use athlete means.

### Historical-evidence impact matrix (operational store, inventoried on a disposable restore)

| Record | Store | Method / computed version | Status | Material impact | Downstream |
|---|---|---|---|---|---|
| `RUN-REAL-0002` | `real_runs.json` | RELIABILITY 1.0.0 | SUPERSEDED (primary result) | ICC 0.951 → 0.889, CI 0.880–0.987 → 0.745–0.969, TE 49.7 → 75.8 N, "SWC" 137.8 N → MDC95 210.1 N, mean CV 4.2 → 6.6% | No evidence, figure or citation |
| `RUN-REAL-0001` | `real_runs.json` | TREND 1.0.0 | SUPERSEDED (diagnostics) | Estimates identical (slope 0.99845, CI 0.622–1.375); Q–Q SD 4.88 → 0.836 | None |
| `RUN-U-0001` / `EVID-U-0001` / `FIG-U-0001` | `research.db` | TREND 1.0.0 | SUPERSEDED (diagnostics, figure intervals) | Estimates identical; occasion-1 band 34.97–42.08 → 34.74–42.31 cm | Cited in frozen report `STUDY-U-60C639BA` v2 |
| `RUN-REAL-0003` | `real_runs.json` | SIGNAL-QA 1.0.0 | CURRENT | None | None |
| `QUAL-REAL-RELIABILITY` 1.0.0 (2026-11-06) | `qualification/real_qualification.json` | — | Superseded receipt | Claimed QUALIFIED for the wrong ICC | Archived under `qualification/history` when qualification next runs |

### Reconciliation demonstrated on the disposable restore (`res619-evidence/reconciliation.json`)

- New 1.1.0 runs are appended: `RUN-REAL-0004` (reliability), `RUN-REAL-0005` (trend) and `RUN-U-0002` (authored trend). Historical SQLite rows and ledger records are byte-identical before and after.
- These actions are refused, each with the supersession reason: promoting `RUN-REAL-0002`, re-citing `EVID-U-0001`, and freezing a report that still cites it.
- Frozen v2 still exports, with the banner. After unciting the old evidence and citing the 1.1.0 evidence, v4 freezes without warnings.
- Qualification re-ran with R. MIXEDLM 1.1.0 and RELIABILITY 1.1.0 are QUALIFIED against the new runs, and SIGNAL 1.0.0 is QUALIFIED. The 2026-11-06 receipt was archived.
- SQLite `integrity_check` = ok, with 0 foreign-key violations.

### Native GUI and figures

`res619-evidence/01..05` were captured from the real `MainWindow` on the restore. They show:
- the GUI reliability run: 1.1.0 CURRENT, ICC 0.8887, matching R exactly;
- the CC0-1.0 · PSEUDONYMOUS pill, taken from the source manifest;
- no stale run after switching studies;
- the historical v2 report preview, with the superseded banner;
- the legacy figure, with its SUPERSEDED title.

`figure-*.png` are the exported Matplotlib figures; PNG, PDF and SVG were all produced. Figure provenance includes the method status, source DOI and licence.

### Installed package (`res619-evidence/installer-smoke.json`)

- Built with `scripts/build_windows.ps1` (PyInstaller onedir + Inno Setup), source commit `c6255bb` (application source identical to `4c014d5`; only documentation differs). The working tree held only the owner's pre-existing `generator_manifest.json` edit.
- Installer `DynamisScience-Setup-x64.exe`, SHA-256 `BF275A0E2457E2539A3F67BB8D0EF935CDBB5E5542B33B738F0EA2C2B085560D`, 141,555,829 bytes.
- `scripts/test_windows_installer.ps1` ran with the disposable restore as its source root. It covers a silent install, the catalogue smoke (onedir, installed, Performance, reopen and post-restore), and installed scientific workers with digests equal to direct runs.
- **RES-619 values from the installed reliability worker:** method 1.1.0, ICC(3,1) 0.8887265872, CI 0.7451953776–0.9692965400, TE 75.782606 N, MDC95 210.054807 N.
- The installed trend worker recorded method 1.1.0 with `CONDITIONAL_PEARSON` residuals and slope 0.99845 cm per occasion.
- The installed real-data qualification passed (MIXEDLM, RELIABILITY and SIGNAL all QUALIFIED), and PNG/PDF/SVG exports carried embedded provenance.
- SQLite integrity was ok, the logical hash was preserved, and the operational database was unchanged. The database survived uninstall, and the temporary root was removed.
- The script's default output file `docs/desktop/evidence/g4-packaging-benchmarks.json` (RES-604/613 evidence) was restored to its committed content; this run's output lives here instead.

### Claims that require independent human or statistical judgement

1. ICC(3,1) vs ICC(2,1) as the primary reliability estimand, and whether mixed-plate trials or IMU-match eligibility should change the analysis set.
2. Whether ML Wald intervals are acceptable with 21 athletes, or whether a profile or Kenward–Roger interval should become the qualified method (RES-590 scope if new estimators are needed).
3. How to interpret the non-normal random intercepts in the trend model.
4. Owner authorization to append 1.1.0 runs and re-cite evidence in the **operational** store.
5. The DataCite "© 2025 The Authors" statement alongside CC0, before any commercial distribution (privacy obligations remain regardless).
