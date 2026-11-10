# RES-619 — Statistical methodology and evidence-validity audit

Audit date: 2026-11-10. Baseline: `e875427` (RES-613). Scope: the existing methods only. New Bayesian, ML and PIML families remain RES-590.

All numbers below come from isolated copies of the admitted snapshots or from pytest's isolated data roots. The private research root `D:\datasets\DynamisScience` was read, never written.

## Method matrix

| Method (catalogue id, version) | Estimand | Eligibility / missingness | Key assumptions | Diagnostics | Evidence class | Main limitations | Code |
|---|---|---|---|---|---|---|---|
| Linear mixed-effects change (`METH-REAL-TREND` 1.1.0) | Population mean within-athlete CMJ-height change per occasion (fixed slope), and model-implied change between two occasions | ≥3 subjects, ≥8 complete rows. Complete case at the outcome, no imputation (MAR assumed) | Linear in occasion. Random intercept + slope per athlete. Normal, homoscedastic within-athlete errors. Occasions are ordinal, not equally spaced time | Optimizer attempts and selection by log-likelihood, convergence, marginal residuals by occasion, **conditional Pearson residual Q–Q**, sample context | **Qualified** against R lme4 (ML) | Single cohort (21 athletes, 4 occasions). ML Wald z intervals with no Satterthwaite/Kenward–Roger correction. Random-intercept fallback changes the estimand's SE basis. Effect size divides by baseline SD and falls back silently to pooled SD | `realanalysis.py:655` (`_fit_trend`), `qualification_real.py:53` |
| Synthetic longitudinal arm × time (`METH-LONG`) | Difference in change between arms | First valid trial per athlete-week | As above, plus arm-specific slopes | As above. Q–Q from `_normal_qq` (z-scored) | **Qualified, synthetic only** (cluster-robust OLS reference for fixed effects) | No external validity. Fallback chain changes the estimator class | `analysis.py:43`, `analysis.py:89`, `analysis.py:289` |
| Repeated-trial reliability (`METH-REAL-RELIABILITY` 1.1.0, synthetic `METH-REL`) | ICC(3,1): consistency of a single trial, trials as a fixed factor. Typical error = √MSE. 95% MDC = 1.96·√2·TE | ≥3 subjects with ≥2 trials. Balanced on the first *k* trials **in acquisition order**. Extra trials are excluded and counted | Two-way ANOVA, subjects random. No subject × trial interaction. Normal errors for the F-based CI | Balanced design, trials used/excluded, Shrout–Fleiss F CI on MSR/MSE, ICC(1,1) and ICC(2,1) sensitivities, per-subject CV | **Qualified** against statsmodels OLS ANOVA and R `aov` | Within-session reliability of peak vertical GRF, not between-day reliability or device agreement. Peak force not normalised to body weight. Walking speed uncontrolled | `analysis.py:367` (`two_way_icc`), `realanalysis.py:628`, `realanalysis.py:992`, `qualification.py:18` |
| Descriptive occasion / activity means (`METH-REAL-DESC`, research descriptive) | Group mean, SD and Student-t 95% CI per occasion | Observed values only; missing counted | Independent observations within an occasion | Counts, missingness | **Descriptive** | No inference across occasions; repeated measures are ignored by the per-occasion CI | `realanalysis.py:614` (`mean_ci_half_width`), `realanalysis.py:886`, `researchanalysis.py:75` |
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

1. Historical runs and evidence in the private ledger (for example `RUN-REAL-*` reliability runs made with method 1.0.0) keep their recorded ICC and Q–Q values, by design. They must be re-run in the app to obtain 1.1.0 results. Until then, regenerating `QUAL-REAL-RELIABILITY` against the private root will correctly report FAILED against those stale runs. Reports already citing the 1.0.0 ICC need owner review.
2. Mixed-model intervals are ML Wald z intervals with 21 athletes. A small-sample correction (Kenward–Roger via `pbkrtest`/`lmerTest`) was not implemented, because no independently qualified Python route exists here.
3. The conditional-residual Q–Q is exploratory: BLUP-based residuals are shrunk and correlated. No formal normality test or random-effect Q–Q is provided. No sensitivity analysis (e.g. robust or REML) is offered.
4. Individual-change "typical error" (change SD/√2 over an intervention block) is not measurement error. The key name is unchanged, to keep the contract stable. The real-data path labels it, but the synthetic path does not.
5. The synthetic generator catalogue (`generate.py`, METH-REL outputs) still names "smallest worthwhile change". It was not edited, to keep the generated `DS-SYNTH-001` manifest and the pre-existing `generator_manifest.json` change untouched.
6. Fitness–fatigue remains a prototype. Body-weight recovery remains rejected.
7. Qt verification is pytest-qt offscreen (figure titles, labels, reference line, legacy fallback). The Windows installer was not rebuilt, and no installed-app or on-screen evidence was recorded for RES-619.
8. No external practitioner or independent human statistical review has taken place (RES-589). This audit is an agent review, cross-checked only against R, statsmodels and the published tables above.
