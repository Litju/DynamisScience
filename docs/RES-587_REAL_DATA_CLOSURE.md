# RES-587 — Real-data admission and scientific qualification

Status: **PARTIALLY QUALIFIED** — all executable engineering and scientific gates
pass; practitioner review and the Linear status write-back are blocked by
external dependencies.

This document records what was actually verified on native Windows on
2026-11-04. It does not replace the immutable JSON records under
`$DYNAMISSCIENCE_DATA_ROOT`, which are the authoritative evidence.

## 1. Storage and isolation

The repository remains proprietary and does not contain third-party data.

```text
$DYNAMISSCIENCE_DATA_ROOT\
    sources\        original downloads, immutable
    extracted\      filtered extraction of the MoveSmart ZIP
    quarantine\     reserved for rejected content (empty)
    admitted\       legacy fixture admission area (empty)
    snapshots\      write-once Parquet snapshots + manifests
    qualification\  R/NumPy reference outputs
    manifests\      source assessments, admissions, quality records
    artifacts\      real runs, evidence, figures, investigations, reports
    reports\        rendered browser validation
    tmp\            staging and pytest temp
```

Measured usage:

| Area | Bytes |
|---|---:|
| sources | 166,300,056 |
| extracted | 675,544,106 |
| snapshots | 58,824,117 |
| qualification | 14,395 |
| manifests | 12,844 |
| artifacts | 491,347 |
| reports | 2,559,951 |
| tmp | 96,701 |
| **total** | **903,843,517** |

Free space on `E:` after admission: approximately **294.8 GB**. The 50 GB
working-capacity target was never approached.

## 2. Real datasets admitted

### A. Mendeley — Sprint Priming, Longitudinal Study

- DOI: `10.17632/6p99569x66.1`
- Publisher: Mendeley Data (Elsevier); creator Patrick Holmberg
- Version: 1; publication 2026-06-11
- File: `DATA.xlsx`, **40,973 bytes**
- SHA-256: `81e5665cb9c547f8a1870a62bca87126db58108cf65e002b1fdf681deb21a9da`
- Licence: **CC BY 4.0** (verified from the Mendeley public API `data_licence`
  field and the Creative Commons deed)
- Commercial use: permitted; redistribution: permitted with attribution
- Privacy: **PSEUDONYMOUS** — integer athlete IDs plus age, height, body mass and
  occasion; participant-level rows are not published from this repository
- Snapshot: `DS-REAL-MENDELEY-2C44490E08AD`
- Content: 168 athlete-occasion-phase rows, 21 athletes, four testing occasions,
  82 post-occasion CMJ/strength rows, 168 sprint rows
- Design: single-arm repeated measures; no concurrent control arm is
  identifiable in the deposited table
- Important limit: **no raw force traces**. The workbook contains derived
  scalars only. CMJ height cannot be independently recomputed from this source.
- Data-quality findings: 2 missing CMJ rows at occasion 4 (subjects 4 and 14);
  4 rows where `BSrel` disagrees with `BS/wt` by more than 0.05; 35 rows where
  the relative isometric value is not exactly reproducible from the deposited
  peak force and body mass; sprint 20 m equals the two 10 m splits to machine
  precision, so the splits are not independent measurements.

### B. Zenodo — MoveSmart wearable IMU + force plate

- DOI: `10.5281/zenodo.17376717`
- Publisher: Zenodo (CERN); creators Ghaffarzadeh, Chakraborty, Aslansefat,
  Dostan, Papadopoulos
- Version: v1.0; publication 2025-11-04
- File: `Dataset.zip`, **166,259,083 bytes**
- MD5: `cc354ea010f622572a24ccd3e6dfd5a9`
- Licence: **CC0 1.0** — this differs from the CC BY 4.0 reported in the earlier
  RES-587 notes; the Zenodo record metadata was checked directly
- Commercial use: permitted; redistribution: permitted
- Privacy: **PSEUDONYMOUS** — participant directories encode birth year, height
  and body mass (for example `P1-1990-186.5-95.8`)
- Privacy incident: the ZIP contains
  `~$rvin_Ghaffarzadeh_IT_Internship_Application.docx`, an unrelated personal
  document. It was excluded from extraction and is never analysed.
- Archive inventory: 3,564 entries, 1,769 CSV files, 676,083,934 uncompressed
  bytes, 0 path-traversal candidates; `__MACOSX`, `.DS_Store` and the personal
  DOCX were excluded.
- Snapshot: `DS-REAL-MOVESMART-805259588272`
- Content: 398 matched force+IMU trials, 10 participants, five activities
  (walking, jogging, running, heel drop, step drop), **5,890,000** native
  1000 Hz force samples and **453,403** Apple Watch samples at approximately
  100 Hz, 120 trials with all three force plates.
- Important limits: no CMJ task (this must not be labelled CMJ data); the
  advertises trial-matching manifest, quality flags, validation results and
  analysis code are absent from the ZIP; only 120/398 trials have all three
  plates; device clocks differ by about four hours with ~15 s variability, so
  sample-level synchronisation cannot be verified; no calibration log.

## 3. Admission pipeline

The existing admission infrastructure was extended, not rebuilt. The real path
is separate from the synthetic fixture path:

```text
verified source assessment
  -> checksum verification
  -> adapter / native parsing
  -> schema, unit and range checks
  -> quality assessment (errors / warnings / quarantined fields)
  -> harmonisation with native values retained
  -> write-once snapshot (atomic staging + checksums)
  -> provenance manifest
  -> admission record
  -> real-data study + cohort + investigation
```

Snapshots are content-addressed and write-protected. Re-registering identical
content returns the existing snapshot; reusing an id for different bytes raises
`SnapshotConflictError` and leaves the original untouched. Tested in
`tests/test_real_admission.py`.

## 4. Independent scientific qualification

### 4.1 Mixed-effects model — Python vs R lme4

Input: `cmj_occasions`, 82 complete observations, 21 athletes, four occasions.
Model: `cmj_height_cm ~ occasion_c + (1 + occasion_c | subject_id)`, ML.

| Estimand | R 4.6.2 / lme4 2.1-0 | DynamisScience | Absolute difference |
|---|---:|---:|---:|
| Intercept | 38.65013281 | 38.65013306 | 2.51e-7 |
| Occasion slope | 0.99845159 | 0.99845121 | 3.77e-7 |
| Slope SE | 0.19161313 | 0.19200835 | 3.95e-4 |
| Log likelihood | −208.31180031 | −208.31180031 | 1.62e-10 |
| Intercept variance | 62.576133 | 62.576236 | 1.03e-4 |
| Slope variance | 0.1679674 | 0.1679586 | 8.84e-6 |
| Residual variance | 2.819243 | 2.819255 | 1.22e-5 |

Pre-declared tolerances: absolute 1e-4 for fixed effects, relative 5e-3 for
standard errors, absolute 1e-3 for log likelihood, relative 1e-3 for variance
components. All pass. Record: `QUAL-REAL-MIXEDLM`, status **QUALIFIED**.

**Finding:** the first L-BFGS fit stopped at logLik −215.824 while lme4 found
−208.312. The production implementation now evaluates L-BFGS-B, BFGS, Powell
and Nelder–Mead and keeps the highest-likelihood converged fit. The pre-fix run
is retained as `RUN-REAL-0001`; the qualified run is `RUN-REAL-0010` and its
evidence is `EVID-REAL-0005` (then re-promoted as later runs reproduced it).

Current result: slope **+0.998 cm per occasion** (95% CI 0.622 to 1.375);
model-implied change occasion 1 → 4 **+3.00 cm** (95% CI 1.87 to 4.12).
Single-arm design: this is a within-athlete change, not a causal intervention
effect.

### 4.2 Reliability — ICC(3,1)

Input: MoveSmart `signal_trials`, walking only; balanced 9 participants × 5
trials = 45 peak vertical GRF values; one participant lacked two walking trials
for the balanced design.

| Quantity | Independent two-way ANOVA | DynamisScience | Difference |
|---|---:|---:|---:|
| ICC(3,1) | 0.9511167659 | 0.9511167659 | 0.0 |
| Typical error | 49.7110 N | 49.7110 N | 0.0 |
| Mean within-subject CV | 4.2061 % | 4.2061 % | 0.0 |

Sensitivity variants: ICC(2,1) = 0.9305; ICC(3,k) = 0.9898. ICC(3,1) is the
primary because participants are random, trials are the fixed repeated measure,
and the reported value is a single measurement with consistency. Record:
`QUAL-REAL-RELIABILITY`, status **QUALIFIED**.

### 4.3 Force signal and integration qualification

- Force sampling: 1000 Hz for every force file; durations 5 or 10 s.
- IMU: median positive-interval rate 99.6–103.1 Hz; duration-based rate shows
  irregular gaps and duplicate timestamps; native timestamps retained.
- Four representative trials were re-derived from the original CSVs with an
  independent NumPy sum, threshold detector and trapezoidal integration:
  peak force and support impulse differences were **0.0** for all four.
- Force saturation: maximum |Fz| below 8,000 N.
- Device clock offset: median approximately **−14,309 s** (about −3.97 h),
  SD ~15 s. Trial matching uses participant + activity + trial number, not
  timestamps. No sample-level synchronization is claimed.
- Body-weight recovery from the support-window mean was tested on walking and
  heel-drop trials: bias **−169 N (−22.9%)**, SD 115 N, 95% limits of agreement
  −395 to +57 N. This estimator is **rejected**, not reported as validated.
- Record: `QUAL-REAL-SIGNAL`, status **QUALIFIED**.

### 4.4 Reliability not estimable from Mendeley

The Mendeley deposit has one CMJ per occasion and no repeated within-session
trial. It cannot support trial-to-trial reliability. This is recorded as a
limitation rather than substituted with a different quantity. The independent
reliability gate is satisfied by the MoveSmart repeated trials.

## 5. Workbench demonstration

The existing Research / Data / Library architecture is reused.

1. `/data/admission` lists both verified sources, rights gates, privacy
   classification, file checksums, admissibility, admission records, snapshots
   and scientific qualification comparisons.
2. `/data/DS-REAL-MENDELEY-2C44490E08AD` shows the immutable Parquet tables,
   SHA-256 checksums, source DOI/licence/privacy, and quality counts.
3. `/research/studies/STUDY-REAL-001` is the real longitudinal workbench:
   registered plan, dataset, cohort, explore, mixed-model analysis, diagnostics,
   evidence promotion, lineage and report.
4. `/research/studies/STUDY-REAL-002` is the measurement workbench: signal
   qualification, reliability, diagnostics, evidence and report.
5. Browser validation ran at **1440×900, 1280×800 and 1024×800** against the
   production Next.js build (`localhost:3001`) with zero console errors, zero
   page errors, zero failed requests, zero horizontal document overflow and all
   expected markers visible on every page. Report:
   `reports/browser/browser_validation.json`.

## 6. Reproduction commands

```powershell
Set-Location (git rev-parse --show-toplevel)
$env:DYNAMISSCIENCE_DATA_ROOT = Join-Path $env:LOCALAPPDATA 'DynamisScience'
$env:DYNAMISSCIENCE_RSCRIPT = (Get-Command Rscript -ErrorAction Stop).Source

# 1. Verify source checksums and write the immutable snapshots
Set-Location .\services\science
.\.venv\Scripts\python.exe -m dynamis_science.ingest_real --source all

# 2. Independent qualification (exports CSV, runs Rscript/lme4, recomputes ICC)
.\.venv\Scripts\python.exe -m dynamis_science.qualification_real

# 3. Python tests
Remove-Item Env:DYNAMISSCIENCE_DATA_ROOT
.\.venv\Scripts\python.exe -m pytest -q

# 4. Backend
$env:DYNAMISSCIENCE_DATA_ROOT = Join-Path $env:LOCALAPPDATA 'DynamisScience'
.\.venv\Scripts\python.exe -m uvicorn dynamis_science.api:app --host 127.0.0.1 --port 8000

# 5. Frontend (new PowerShell)
Set-Location (Join-Path (git rev-parse --show-toplevel) 'apps\web')
$env:NEXT_PUBLIC_SCIENCE_API_URL = 'http://127.0.0.1:8000'
.\node_modules\.bin\next.cmd dev -p 3000

# 6. Production build and rendered validation
.\node_modules\.bin\next.cmd build
.\node_modules\.bin\next.cmd start -p 3001

# 7. Browser validation against production
Set-Location (Join-Path (git rev-parse --show-toplevel) 'services\science')
$env:DYNAMISSCIENCE_DATA_ROOT = Join-Path $env:LOCALAPPDATA 'DynamisScience'
$env:DYNAMISSCIENCE_BROWSER_BASE = 'http://localhost:3001'
.\.venv\Scripts\python.exe scripts\browser_validation.py
```

`pnpm` and `npm` corepack shims were broken on this machine; the equivalent
direct Node binaries under `apps/web/node_modules/.bin` were used. Playwright
uses the installed Microsoft Edge, so no browser download is required. R and
lme4 are installed under `configured R installation` (R 4.6.2, lme4 2.1-0).

## 7. Acceptance matrix

| # | Criterion | Status | Evidence / limitation |
|---:|---|---|---|
| 1 | Real longitudinal data admitted | **PASS** | Mendeley snapshot, 168 rows / 82 CMJ |
| 2 | Real complementary modality admitted | **PASS** | MoveSmart snapshot, 398 matched trials / 5.89M force samples |
| 3 | Source licensing and privacy reviewed | **PASS** | CC BY 4.0 and CC0 1.0 verified; privacy incidents recorded |
| 4 | Scientific measurement qualification | **PASS** | 1000 Hz, support detection, 4 trials re-derived exactly; body-weight estimator rejected |
| 5 | Independent reliability qualification | **PASS** | ICC(3,1) 0.9511, TE 49.711 N, CV 4.206%, exact independent recomputation |
| 6 | Independent MixedLM qualification | **PASS** | R lme4 comparison; optimizer defect found and fixed; pre-fix run retained |
| 7 | Data quality and comparability | **PASS WITH LIMITATIONS** | 2 missing CMJ, 4 BSrel inconsistencies, no raw traces, no sample-level IMU sync, no CMJ in MoveSmart |
| 8 | Source-to-evidence provenance | **PASS** | 11-node / 13-edge lineage from DOI source to report |
| 9 | Real-data workbench execution | **PASS** | Run, diagnostics, promote, cite, report, lineage demonstrated |
| 10 | Reproducible scientific reporting | **PASS** | Report cites evidence, run, spec, cohort, snapshot, DOI/licence and limitations |
| 11 | Synthetic MVP regression | **PASS** | 62 Python tests, 30 frontend tests, production build, synthetic study untouched |
| 12 | Browser UX validation | **PASS** | 1440/1280/1024 production browser; 0 console/page errors, 0 failed requests, 0 overflow |
| 13 | Practitioner feedback/validation | **BLOCKED** | Requires a human sports scientist / practitioner; no interview was fabricated |

## 8. External blockers

1. **Practitioner review** — no qualified practitioner was available in this
   run. This gate cannot be fabricated or inferred from code.
2. **Linear write-back** — no Linear API tool or credential is exposed in this
   execution environment. The status text below is ready to post.
3. **MoveSmart advertised artefacts** — the deposit lacks the trial-matching
   manifest, quality flags, validation results and analysis code described on
   its record page. The workaround is documented, but the missing files cannot
   be manufactured.
4. **Mendeley raw force traces** — not deposited. Force-signal qualification is
   therefore performed on MoveSmart, not on the longitudinal study.
5. **Mendeley study-week mapping** — COND 1–4 are not mapped to calendar weeks;
   analyses use occasion, not invented weeks.

## 9. Linear status update (prepared, not posted)

> **RES-587 — Windows closure, 2026-11-04**
>
> Real-data admission is complete for two rights-verified sources:
> (1) Mendeley Sprint Priming `10.17632/6p99569x66.1`, CC BY 4.0, 40,973 B,
> 21 athletes × 4 occasions, derived CMJ/strength/sprint rows, no raw traces;
> (2) Zenodo MoveSmart `10.5281/zenodo.17376717`, CC0 1.0 (not CC BY 4.0 as
> previously noted), 166,259,083 B, 398 matched force+IMU trials, 5.89M native
> 1000 Hz force samples. Both are admitted as write-once snapshots outside the
> public repository.
>
> Scientific qualification: MixedLM matches R 4.6.2 lme4 2.1-0 after fixing an
> optimizer-selection defect (slope 0.99845 cm/occasion, change 1→4 +3.00 cm,
> 95% CI 1.87–4.12; logLik −208.3118). ICC(3,1) for walking peak vertical GRF
> is 0.9511 (95% CI 0.8795–0.9870), TE 49.711 N, CV 4.206%, independently
> reproduced. Force integration was re-derived exactly on four representative
> trials. Body-weight recovery from the support-window mean was tested and
> rejected (bias −169 N, −22.9%).
>
> Workbench/browser: production Next.js build validated at 1440×900, 1280×800
> and 1024×800 with zero console errors, page errors, failed requests or
> overflow. Evidence promotion, report citation and 11-node lineage verified.
>
> Status: **PARTIALLY QUALIFIED**. Remaining blocker: practitioner review.
> Linear write-back was unavailable in the execution environment. Synthetic MVP
> remains functional (62 Python tests, 30 frontend tests, production build).
