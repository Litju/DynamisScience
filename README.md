# DynamisScience

DynamisScience is a local-first scientific workbench for sports scientists. It is the scientific computation and evidence layer of the broader DynamisSystems ecosystem: a question becomes a cohort, an exploration, an analysis with diagnostics, an immutable evidence artifact and, finally, a reproducible report — inside one persistent study workspace.

The MVP is deliberately not an athlete-management system, a BI dashboard, or an AI chat surface.

## Product philosophy

```text
Question → Data → Cohort → Exploration → Analysis → Diagnostics → Evidence → Interpretation → Report
```

The computational boundary stays visible:

- `DatasetSnapshot` is an immutable analytical input.
- `AnalysisSpec` is the machine-readable authority for an execution; the frozen plan decides what is `PLANNED` and what is `EXPLORATORY`.
- `AnalysisRun` is append-only and retains its environment, diagnostics, reproducibility key and result digest.
- `EvidenceArtifact` exists only after an explicit promotion of a completed run.
- `MetricDefinition` distinguishes methods even when units match.
- Lineage is computed from stored artifacts and opened from any artifact, not a destination.

## Product structure

The global navigation is small: **Research**, **Data**, **Library**.

| Route | Purpose |
| --- | --- |
| `/research` | Research contexts; STUDY-001 is the implemented study |
| `/research/studies/STUDY-001` | Study Workbench: study tree · ordered investigation · contextual inspector |
| `/research/studies/STUDY-001?mode=report` | The evidence-driven report, inside the same workspace |
| `/data/DS-SYNTH-001` | Snapshot tables, schemas, row counts, checksums, quality, synthetic disclaimer |
| `/library?tab=metrics` | Metrics, Protocols, Methods and Models executed by the workbench |

Inside the study, the investigation `INV-001 · Primary Intervention Analysis` is an ordered, typed, serialisable block document persisted by the science service:

```text
Question → Dataset → Cohort → Explore → Analysis → Diagnostics → Evidence → Figure → Interpretation → Report Section
```

Blocks reference domain objects (spec, run, evidence and figure IDs); they never hold scientific values. Explore, Analysis, Match Event, Model, Table and Interpretation blocks can be added, an Analysis can be forked, and reordering is only allowed when every block stays below the blocks it depends on.

Focused viewers open over the workbench and return to the same investigation state:

- **Force signal** — 1000 Hz vertical GRF of a selected CMJ trial with body-weight reference, phase boundaries, derived metrics and an Evidence Passport per metric.
- **Spatial + biomechanical** — synchronized 10 Hz field and pose playback for match events, finite-difference kinematics, joint-angle approximations, and an explicit unavailable state for players without pose.
- **Lineage** — the computed provenance DAG of any artifact (ancestors complete, consumers bounded) with stored metadata per node.
- **Run history** — the immutable execution ledger.

Linked selections (athlete, week, trial, match event, active cohort, run) are always visible in the context strip. `Ctrl/Cmd + K` opens a navigation-only command palette.

## Architecture

```text
DynamisScience/
├─ apps/web/                    Next.js + React + TypeScript workbench
│  ├─ app/                      Research, Data, Library and study routes
│  ├─ components/workbench/     study shell, tree, inspector, typed blocks
│  ├─ components/viewers/       force, match, lineage, run history
│  ├─ components/report/        report composition from cited artifacts
│  └─ lib/                      contracts, block model, lineage layout
├─ services/science/            FastAPI, generator, analysis, lineage, tests
├─ data/parquet/                local analytical tables (generated)
└─ data/artifacts/              runs, evidence, figures, report, investigation (generated)
```

Parquet is the analytical store; exploration is aggregated server-side with DuckDB, other reads use Polars. Everything runs locally; there are no API keys, hosted models, cloud services or paid dependencies. Fonts are self-hosted npm packages.

## Local setup

Requirements: Node.js 20+, pnpm 11+, Python 3.12+, [`uv`](https://docs.astral.sh/uv/).

```bash
pnpm install
pnpm data:generate
pnpm dev
```

Open `http://localhost:3000`. The science service runs at `http://localhost:8000` (OpenAPI at `/docs`). `pnpm data:generate` also resets the local artifact store — runs, evidence, report citations and the investigation document — to the deterministic seed state.

The generator uses the fixed seed `20260924` and creates 28 synthetic athletes (14 intervention, 14 comparison), 16 weekly observations with two CMJ trials per week, 1000 Hz force traces for audit weeks 1, 6, 10, 12 and 16, weekly load and wellness, a 10 Hz 1,800-frame match segment with four annotated events, pose for four players, one flagged trial and realistic missingness.

## Science service API

```text
GET  /health
GET  /studies                         GET /studies/{id}
GET  /subjects                        GET /subjects/{id}/longitudinal?metric_id=
POST /cohorts/resolve                 cohort definition, counts and missingness for a selection
GET  /explore/longitudinal            DuckDB athlete-week aggregation, arm mean ± 95% CI, context
GET  /force/trials                    GET /force/trials/{id}
GET  /match/{id}                      GET /match/{id}/tracking   GET /match/{id}/pose?athlete_id=
GET  /library                         GET /registry
GET  /datasets                        GET /datasets/{id}
POST /analyses/execute                appends an immutable run (never creates evidence)
GET  /runs                            GET /runs/{id}
POST /evidence                        explicit, idempotent promotion of a completed run
GET  /evidence                        GET /evidence/{id}
GET  /figures                         GET /figures/{id}      figure artifact with computed data
GET  /report                          POST /report/citations   DELETE /report/citations/{id}
GET  /investigations                  GET|PUT /investigations/{id}   ordered block document
GET  /lineage/{id}?scope=path&depth=  computed provenance of an artifact
GET  /models/training-response        POST /models/training-response/scenario
```

Execution resolves each request against the frozen plan. The same method, outcome, parameters and frozen cohort map to the frozen spec (`PLANNED`); anything else becomes a content-addressed exploratory spec and, for a changed cohort, a stable draft cohort (`EXPLORATORY`). A re-execution with the same reproducibility key and result digest is reported as reproducing the earlier run.

## Scientific methods

### CMJ metric extraction

Force traces are labelled through quiet standing, unweighting, braking, propulsion, flight and landing. Jump height (flight time), concentric impulse, braking impulse and duration, countermovement depth, peak force, peak power and RSI-mod are calculated from the trace.

### Group longitudinal analysis

```text
outcome ~ week + group + week:group      (week centred on the reference week)
athlete random intercept + random week slope, first valid weekly trial
```

The estimator ladder is MixedLM random slope → MixedLM random intercept → GEE exchangeable → athlete-clustered OLS; the estimator used and any failed attempts are recorded. The primary estimand, frozen in `PLAN-001`, is the **difference in change from week 1 to week 10, intervention minus comparison**, reported with SE and a Wald 95% CI; the cross-sectional week-10 difference and baseline balance are secondary contrasts. Every run carries computed diagnostics: residual summary, mean residual by week, a normal QQ of standardised residuals, residual SD by arm, sample and missingness context, assumptions and limitations. `SPEC-LONG-001` (concentric impulse) and `SPEC-LONG-002` (eccentric braking duration) cover the two primary outcomes.

### Reliability and individual change

Repeated valid baseline trials give ICC(3,1) with Shrout–Fleiss 95% CI, within-subject CV, typical error (√MSE) and the smallest worthwhile change. Individual change compares weeks 1–2 with weeks 9–10 descriptively against the typical error of a change.

### Training-response prototype

The Model block fits a fitness–fatigue impulse-response model to the cohort-mean weekly training impulse and first-trial concentric impulse by deterministic grid search and exposes fitted parameters, observed and modelled series, residuals and RMSE. Future load scenarios (maintain, taper, overload, custom) are simulated forward with the fitted parameters and fit-window transform, so weeks 1–16 reproduce the fitted series exactly. The block states the computed fit quality; Bayesian, ML, physics-informed ML and differentiable biomechanics are listed only as unavailable categories.

## Validation

```bash
pnpm data:generate
pnpm test
pnpm lint
pnpm typecheck
pnpm build
```

The Python suite covers deterministic regeneration, dataset structure, force metrics, reliability, the difference-in-change estimand, computed diagnostics, planned-versus-exploratory resolution, immutable runs, explicit and idempotent promotion, reproduction detection, cohort resolution, exploration, path-scoped lineage, investigation ordering rules, scenario simulation and report citations. The web suite covers the typed block model, lineage layout, numeric display, report composition, match kinematics, scenario construction and run freshness.

## Known MVP limitations

- The dataset is synthetic and has no external validity.
- Force signals are internally coherent demonstrations; flight time and propulsive impulse are generated independently, so the impulse-momentum jump-height definition exists in the Library but is not materialised in the snapshot.
- The longitudinal model uses a linear week term; the week-11 load spike and week-12 suppression appear as structured residuals.
- The training-response model is an aggregate prototype; on this dataset its standardised fit RMSE is above 1, which the Model block states explicitly.
- Local JSON metadata is a replaceable adapter, not a production metadata database; there is no authentication or multi-tenant control plane.
