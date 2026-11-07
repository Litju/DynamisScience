<div align="center">

# DynamisScience

**A local sports-science operating system connecting daily performance work to reproducible research and evidence.**

![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-local%20service-009688?logo=fastapi&logoColor=white)
![Next.js 15](https://img.shields.io/badge/Next.js-15-000000?logo=nextdotjs&logoColor=white)
![TypeScript strict](https://img.shields.io/badge/TypeScript-strict-3178C6?logo=typescript&logoColor=white)
![statsmodels](https://img.shields.io/badge/statsmodels-MixedLM-4B8BBE)
![DuckDB + Polars](https://img.shields.io/badge/DuckDB%20%2B%20Polars-Parquet-FFF000?logo=duckdb&logoColor=black)
![Licence](https://img.shields.io/badge/licence-All%20rights%20reserved-B22222)

![The Study Workbench](docs/screenshots/workbench.png)

</div>

---

## Dynamis Performance OS

Six connected workspaces cover the practitioner lifecycle: **Today → Plan → Monitor → Test → Research → Report**. Research remains a full scientific environment inside the OS, with projects, studies, immutable snapshots, analyses, evidence, provenance and reports.

![Dynamis Performance OS Squad Command](docs/design/res588-ux/implemented/today-1440.png)

## Why this exists

Sports scientists usually work across disconnected tools: an athlete-management dashboard, a force-plate export, a spreadsheet, a stats script, and a slide deck at the end. At each hand-off the context is lost — which athletes, which trials, which exclusions, which model, which version of the result.

DynamisScience treats the **study** as the unit of work. A scientist opens a study and follows a single investigation:

```text
Question → Data → Cohort → Exploration → Analysis → Diagnostics → Evidence → Interpretation → Report
```

Every number on screen is computed from data, every result carries its uncertainty and diagnostics, and every artifact can be traced back to the measurement it came from. It is designed to feel like a **scientific IDE crossed with a laboratory instrument**, not a KPI dashboard.

> The demonstration study, *CMJ Response to 8-Week Strength Intervention*, runs on a fully **synthetic**, deterministically generated dataset (28 athletes, 16 weeks, 1000 Hz force traces, 10 Hz match tracking and pose). No real athletes or measurements are involved.

## Highlights

- **Persistent research projects.** Projects contain scientist-authored studies, monitoring programs and named investigations. Studies, cohorts, frozen plans, runs, evidence and report versions are stored in a transactional local SQLite store, while admitted Parquet snapshots remain immutable.
- **One persistent study workspace.** Study tree · ordered investigation · contextual inspector, with resizable and collapsible panes and a context strip showing exactly which cohort, run, athlete, trial and event are linked.
- **Typed, serialisable investigation.** The workbench is an ordered document of typed blocks (Question, Dataset, Cohort, Explore, Analysis, Diagnostics, Evidence, Figure, Model, Match Event, Interpretation, Report Section). Blocks reference domain objects by ID and never hold scientific values themselves; the service persists the document with version checks and rejects orderings that break dependencies.
- **Pre-registration that means something.** A frozen analysis plan defines the primary estimand — *difference in change from week 1 to week 10, intervention minus comparison*. Executions that match a frozen spec are `PLANNED`; any change of method, outcome, parameters, cohort or exclusions produces a content-addressed `EXPLORATORY` spec instead of silently rewriting the plan.
- **Immutable runs, explicit evidence.** Runs are append-only and carry software versions, a reproducibility key and a result digest, so a re-execution is recognised as *reproducing* an earlier run. An `EvidenceArtifact` exists only after an explicit, idempotent promotion — and only if diagnostics exist.
- **Diagnostics are part of the chain.** Estimator ladder and fallbacks, residuals by week, normal QQ of standardised residuals, residual spread by arm, sample and missingness context, and stated assumptions — all computed, none decorative.
- **Instruments, not dashboards.** A 1000 Hz force-signal viewer with phase boundaries and a per-metric *Evidence Passport*, and a synchronized 3D field + pose viewer for match events, both opening over the investigation and returning to exactly the same state.
- **Contextual lineage.** Any artifact opens its computed provenance DAG: generator → trials → metric definitions → snapshot → cohort → spec → run → evidence → figure → report.
- **Honest modelling.** A fitted fitness–fatigue model with forward load scenarios, labelled as a mechanistic prototype, which reports its own poor fit rather than hiding it. ML, Bayesian and physics-informed methods are listed as unavailable, never faked.
- **Local and zero-cost.** No API keys, hosted models, cloud services or paid dependencies. Parquet + DuckDB + Polars, FastAPI, Next.js.

## A walk through the study

| | |
|---|---|
| ![Explore](docs/screenshots/explore.png) | **Longitudinal exploration.** Arm means with t-based 95% intervals across athletes, every athlete as a trace, the strength block, a *computed* week-11 load peak and a training-load / match-exposure overlay. Missing and excluded trials stay visible. |
| ![Athlete drill-down](docs/screenshots/explore-athlete.png) | **Linked athlete selection.** Selecting an athlete highlights them everywhere, shows baseline-to-post change against the typical error of a change, and exposes every trial by week — including which have raw traces and which were excluded, and why. |
| ![Force viewer](docs/screenshots/force-viewer.png) | **Force signal viewer.** The real 1000 Hz vertical GRF on a true time axis with body-weight reference, onset, unweighting, braking, propulsion, takeoff and landing. Each derived metric opens an Evidence Passport resolving to its MetricDefinition, algorithm, protocol, snapshot and checksum. |
| ![Analysis](docs/screenshots/analysis.png) | **Analysis execution.** A MixedLM with athlete random intercept and slope; the primary difference-in-change contrast with SE, Wald 95% CI and an interval plot, secondary contrasts, and a new immutable run recognised as reproducing the seeded one. |
| ![Diagnostics](docs/screenshots/diagnostics.png) | **Diagnostics attached to the run.** Convergence and fallbacks, baseline balance, residual summary, residuals by week (showing where a linear term misfits the load spike), a normal QQ plot, and explicit assumptions and limitations. |
| ![Evidence](docs/screenshots/evidence.png) | **Evidence promotion.** The run becomes an immutable, `CONFIRMATORY` EvidenceArtifact bound to its spec, cohort, dataset, checksum and diagnostics, with actions to inspect run, methodology, diagnostics and lineage, or add it to the report. |
| ![Lineage](docs/screenshots/lineage.png) | **Contextual lineage.** A layered provenance DAG computed from stored artifacts; selecting any node shows its stored record. |
| ![Match viewer](docs/screenshots/match-viewer.png) | **Spatial + biomechanical viewer.** Field, ball and articulated pose on one 10 Hz clock; event seeking, bounded playback, finite-difference kinematics, joint-angle approximations, and an explicit unavailable state for players without pose. |
| ![Model](docs/screenshots/model.png) | **Mechanistic model block.** Observed versus fitted response, fitted parameters, solver grid, residuals, and a forward scenario whose output changes as the load plan changes. |
| ![Report](docs/screenshots/report.png) | **Evidence-driven report.** Built from cited evidence and figures; every number links back to its evidence, run and spec, and independent reproductions are reported once with their provenance. |
| ![Library](docs/screenshots/library.png) | **Scientific Library.** Metrics, protocols, methods and models — the same contracts the workbench executes. Two jump-height definitions share a unit but remain distinct definitions. |
| ![Data](docs/screenshots/data.png) | **Dataset surface.** Tables, schemas, null counts, row counts verified against the manifest, SHA-256 checksums, quality and the synthetic-data disclaimer. |

## Architecture

```mermaid
flowchart LR
  subgraph Web["apps/web · Next.js 15 · React 19 · strict TypeScript"]
    R[Research · Data · Library]
    W[Study Workbench<br/>tree · typed blocks · inspector]
    V[Force · Match · Lineage · Run history viewers]
    P[Report composition]
  end
  subgraph Service["services/science · FastAPI · Pydantic"]
    X[Execution & plan resolution]
    E[Evidence promotion & report citations]
    L[Lineage engine]
    M[Fitness–fatigue model]
    Q[DuckDB exploration]
  end
  subgraph Store["Local artifact store"]
    PQ[(Parquet snapshot<br/>DS-SYNTH-001)]
    J[(Runs · evidence · figures ·<br/>report · investigation)]
  end
  G[Deterministic generator<br/>seed 20260924] --> PQ
  G --> J
  Web -- JSON over HTTP --> Service
  X --> PQ
  X --> J
  Q --> PQ
  E --> J
  L --> J
```

```text
DynamisScience/
├─ apps/web/
│  ├─ app/                      Research, Data, Library and study routes
│  ├─ components/workbench/     workspace shell, study tree, inspector, typed blocks
│  ├─ components/viewers/       force signal, match field + pose, lineage, run history
│  ├─ components/report/        report composition from cited artifacts
│  └─ lib/                      contracts, typed block model, lineage layout, display rules
├─ services/science/
│  ├─ dynamis_science/          generate · analysis · lineage · api
│  └─ tests/                    scientific and API contract tests
└─ docs/screenshots/
```

### Engineering decisions worth noting

- **The GUI is not the scientific authority.** Blocks hold references and configuration; values always come from the service, which computes them from the snapshot.
- **Content-addressed specifications and cohorts.** Identical configurations resolve to the same exploratory spec and draft cohort, which is what makes reproduction detection meaningful.
- **Reproducibility digest.** Runs hash their scientific payload (not timing or environment), so "this re-run reproduces RUN-0001" is a computed statement.
- **Evidence classes.** `CONFIRMATORY` (planned inferential), `PLANNED` (planned supporting) and `EXPLORATORY`; superseded evidence is derived, not hand-set.
- **Bounded payloads.** Aggregation happens server-side (DuckDB over Parquet); the browser receives athlete-week summaries and bounded traces, never whole tables.
- **Fit-consistent forward simulation.** Scenarios reuse the fitted parameters and the fit-window transform, so weeks 1–16 reproduce the fitted series exactly before extrapolating.

## Scientific methods

| Area | Method |
| --- | --- |
| CMJ metrics | Phase-aware extraction from 1000 Hz traces: flight-time jump height, concentric and braking impulse (trapezoidal net-force integration), braking duration, countermovement depth, peak force and power, RSI-mod |
| Intervention effect | `outcome ~ week + group + week:group`, week centred on week 1, athlete random intercept + slope (MixedLM), estimator ladder to GEE and cluster-robust OLS, primary contrast = difference in change week 1 → 10 with Wald 95% CI |
| Reliability | Balanced ICC(3,1) with Shrout–Fleiss 95% CI, within-subject CV, typical error (√MSE), smallest worthwhile change |
| Individual change | Baseline (weeks 1–2) vs post-block (weeks 9–10), standardised change, comparison with the typical error of a change — descriptive, not causal |
| Exploration | Athlete-week means of valid trials, arm mean ± t-based 95% CI across athletes, computed load peaks |
| Match context | Speed from tracking velocity, finite-difference acceleration, distance to ball, nearest opponent, geometric joint angles |
| Training response | Fitness–fatigue impulse-response model fitted by deterministic grid search, with residuals, RMSE and forward scenarios |

## Tech stack

**Science service:** Python 3.12 · FastAPI · Pydantic · NumPy · SciPy · statsmodels · Polars · DuckDB · PyArrow · pytest · uv
**Web:** Next.js 15 (App Router) · React 19 · strict TypeScript · TanStack Query · ECharts · React Flow · React Three Fiber / three.js · Vitest + Testing Library · self-hosted IBM Plex

## Running it locally

```powershell
git clone https://github.com/Litju/DynamisScience.git
Set-Location .\DynamisScience
```

Requirements: Node.js 22+, the repository-pinned pnpm 11.24.0, Python 3.12+ and [`uv`](https://docs.astral.sh/uv/). pnpm 11 requires Node.js 22 or newer ([pnpm compatibility](https://pnpm.io/installation)). Local R is needed only for the independent MixedLM qualification; Playwright Chromium is needed only for browser validation.

```bash
npm install --global pnpm@11.24.0
uv sync --locked --directory services/science
pnpm install --frozen-lockfile
```

Set an absolute private data directory outside the repository before starting the full research workflow. On Windows:

```powershell
$env:DYNAMISSCIENCE_DATA_ROOT = 'D:\datasets\DynamisScience'
$env:NEXT_PUBLIC_SCIENCE_API_URL = 'http://127.0.0.1:8000'
$env:DYNAMISSCIENCE_SCIENCE_API = 'http://127.0.0.1:8000'
$env:DYNAMISSCIENCE_BROWSER_BASE = 'http://127.0.0.1:3001'
pnpm dev
```

The root `dev` command regenerates only the deterministic synthetic portfolio and starts the API and frontend. It binds the API to `127.0.0.1:8000` and Next.js to `127.0.0.1:3001`. Open <http://127.0.0.1:3001>; the API's OpenAPI documentation is at <http://127.0.0.1:8000/docs>. The committed development commands have fixed loopback bindings; do not expose the unauthenticated local service to a LAN. A future authenticated pilot requires a separate deployment topology and security review.

Private real datasets, admitted snapshots, manifests, evidence, reports and local research state stay outside GitHub. `DYNAMISSCIENCE_DATA_ROOT` must be an absolute directory outside the checkout. Real-data storage fails closed when it is missing, points inside the repository, or names a file. The resolver reads the environment when called, so tests and tools can supply an isolated root without import-time environment capture.

The private root contains `sources/` (archives), `extracted/`, `admitted/` (legacy upload path), `snapshots/` (immutable real-data tables), `manifests/`, `artifacts/`, `qualification/`, `reports/`, `performance/`, `research/research.db`, and `tmp/`. Synthetic demo fixtures remain in the ignored repository `data/` tree. Existing local fixture artifacts are not migrated automatically.

### SQLite backup and recovery

Use the SQLite Online Backup API so committed WAL records are included. Backups stay under the private root and the recovery command refuses to overwrite an existing file or restore directory:

```powershell
$root = $env:DYNAMISSCIENCE_DATA_ROOT
$backup = Join-Path $root 'backups\research-manual.sqlite3'
$restore = Join-Path $root 'tmp\restore-manual'
uv run --directory services/science python -m scripts.sqlite_recovery backup --destination $backup
uv run --directory services/science python -m scripts.sqlite_recovery verify --database (Join-Path $root 'research\research.db')
uv run --directory services/science python -m scripts.sqlite_recovery restore --backup $backup --destination-root $restore
uv run --directory services/science python -m scripts.sqlite_recovery verify --database (Join-Path $restore 'research\research.db')
```

`restore` writes to a new `tmp/` root, checks the schema, all table counts and logical record hash, checks integrity and foreign keys, reopens through the application persistence layer, and verifies evidence lineage. It copies the existing snapshots, manifests and qualification receipt needed by that check. This procedure verifies SQLite recovery; a full private-root disaster recovery also needs a private backup of archives and other root files. Do not replace the operational database with the verification restore.

## Testing and validation

```bash
pnpm data:generate
pnpm test        # Vitest (web) + pytest (science; isolated private root)
pnpm lint
pnpm typecheck
pnpm build
```

For rendered browser validation, install Playwright's managed Chromium once:

```powershell
uv run --directory services/science playwright install chromium
```

- **136 automated tests** (101 Python, 35 web) covering byte-deterministic regeneration, dataset structure, force-metric correctness, reliability maths, the difference-in-change estimand, computed diagnostics, planned-versus-exploratory resolution, run immutability, idempotent evidence promotion, reproduction detection, cohort resolution, exploration aggregates, path-scoped lineage, research lifecycle and report immutability, monitoring schedules, private-root isolation, archive safety, and SQLite recovery.
- **Rendered end-to-end validation**: scripted headless-browser walkthroughs of the synthetic and real workflows, and of both RES-588 demonstrations, at 1440×900, 1280×800 and 1024×800 against the production build, with zero console/page/network errors and no horizontal overflow.

Python's `tests/conftest.py` replaces any inherited operational root before test modules load, blocks that inherited path, and constrains storage to temporary directories. The regression suite verifies a disposable simulated operational root, including sentinel and SQLite/WAL file hashes. `pnpm test` needs no manual environment cleanup. For rendered checks, install Chromium with `uv run --directory services/science playwright install chromium`, then run `uv run --directory services/science python -m scripts.browser_validation` and `uv run --directory services/science python -m scripts.performance_os_smoke` while `pnpm dev` is running.

## Real-data admission (RES-587)

Two rights-verified public datasets are admitted outside the public repository
through the same workbench: Holmberg Sprint Priming (Mendeley, CC BY 4.0) and
MoveSmart wearable IMU + force plate (Zenodo, CC0 1.0). The admission pipeline
writes write-once Parquet snapshots with checksums and provenance, and the real
studies run independent MixedLM, ICC(3,1) reliability and force-signal
qualification. See [docs/RES-587_REAL_DATA_CLOSURE.md](docs/RES-587_REAL_DATA_CLOSURE.md)
for identities, rights, measured storage, numerical comparisons, commands and
the acceptance matrix.

## Complete research lifecycle (RES-588)

A scientist can originate a research project from a blank workspace, author a
study or monitoring program, bind an admitted snapshot, build a declarative
cohort, freeze and fork an analysis plan, execute qualified methods, promote
evidence and export a versioned HTML report. Research is one of the six integrated
Performance OS workspaces; its scientific workbench and capabilities remain available there.

| | |
|---|---|
| ![Research projects](docs/screenshots/res588-research.png) | **Projects and monitoring programs.** Projects persist objectives, associated admitted datasets, studies, programs and version history. |
| ![Study setup](docs/screenshots/res588-setup.png) | **Authoring and qualification.** Frozen plan, content hash, cohort binding and registered method eligibility — including the explicitly rejected body-weight estimator. |
| ![Longitudinal analysis](docs/screenshots/res588-analysis.png) | **Real longitudinal execution.** The Mendeley study gives a within-athlete CMJ change of +3.00 cm (95% CI 1.87–4.12), matching the R/lme4-qualified implementation. |
| ![Evidence report](docs/screenshots/res588-report.png) | **Versioned evidence report.** Cited evidence and figure, frozen report version, embedded provenance manifest and a working standalone HTML export. |
| ![Measurement workflow](docs/screenshots/res588-measurement.png) | **A second real-data workflow.** MoveSmart repeated walking trials give ICC(3,1) 0.9511 (95% CI 0.8795–0.9870), typical error 49.711 N and CV 4.206%. |
| ![Monitoring program](docs/screenshots/res588-monitoring.png) | **Prospective monitoring.** Eight planned weekly measurements are kept distinct from four available historical readings; a planned point without a reading is MISSING, never zero. |

Both demonstrations were created from blank projects through the production UI,
executed, promoted to evidence, exported, and reopened after a full service and
web restart. See [docs/RES-588_RESEARCH_LIFECYCLE.md](docs/RES-588_RESEARCH_LIFECYCLE.md)
for exact IDs, results, commands, browser receipts, commits and the PASS/FAIL/
BLOCKED matrix.

## Status and limitations

This is a vertical-slice MVP built to demonstrate the product and its scientific discipline.

- The operational squad fixture is synthetic and has no external validity. Rights-verified Mendeley and MoveSmart research datasets are admitted separately and remain outside the public repository.
- Force traces are internally coherent demonstrations; flight time and propulsive impulse are generated independently, so the impulse-momentum jump-height definition is registered but deliberately not materialised.
- The longitudinal model uses a linear week term; the week-11 load spike and week-12 suppression appear as structured residuals, which the diagnostics surface.
- The training-response model is an aggregate prototype; on this dataset its standardised fit RMSE exceeds 1, which the workbench states explicitly.
- Mutable research metadata lives in a transactional local SQLite store; admitted snapshots stay write-once. There is no authentication or multi-tenancy.
- Monitoring schedules are prospective plans, not observations; a planned measurement without a reading is MISSING and no readiness, fatigue or injury score is inferred.

## Licence

**Copyright © 2026 Julio Rodriguez. All rights reserved.**

This repository is public for portfolio viewing only. No permission is granted to copy, distribute, modify, deploy or otherwise use any part of it without prior written permission. See [LICENSE](LICENSE) for the full terms.
