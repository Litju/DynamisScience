# RES-588 — Dynamis Performance OS P0/P1 Implementation

Status: **implemented and validated; awaiting owner product acceptance.**
Date: 2026-11-06 · Native Windows / PowerShell · local synthetic fixture
`DS-SYNTH-001` (28 football athletes, 16 weeks), with admitted real datasets kept
strictly in the research workspace.

This document is the implementation record, feature/availability matrix,
validation record and acceptance matrix. It is not a new design proposal. The
approved visual authority is:

- `docs/design/res588-ux/SPORTS_SCIENCE_DESIGN_PATTERN.md`
- `docs/design/res588-ux/prototypes/f/command.html`
- `docs/design/res588-ux/prototypes/f/atlas.html`
- `docs/design/res588-ux/screens/f-command-1440x900.png`
- `docs/design/res588-ux/screens/f-atlas-1440x900.png`

Implemented screenshots are in `docs/design/res588-ux/implemented/`.

## 1. What was built

Six integrated workspaces share one context, one athlete identity and one unit
registry:

| Workspace | Route | Primary question |
|---|---|---|
| **Today** | `/today` | Who needs attention now? |
| **Plan** | `/plan` | What should we do this week and block? |
| **Monitor** | `/monitor` | What is changing over time? |
| **Test** | `/test` | What can the athlete do, and how reliable is it? |
| **Research** | `/research` | What does the evidence support? |
| **Report** | `/report` | What does each audience need to know? |

Supporting surfaces:

- `/athletes/[athleteId]` — Athlete 360.
- `/atlas` — Component & unit atlas, status language, thresholds, module map.
- `/research/projects/[projectId]` and `/research/studies/[studyId]` — the existing
  scientific workbench, preserved and reachable from the Research workspace.
- `/data`, `/data/admission`, `/library`, `/data/[snapshotId]` — existing data
  admission and registry surfaces, preserved.

## 2. Data and provenance

### Squad workspaces

All Today, Plan, Monitor, Test and Athlete 360 values are computed from the
immutable deterministic snapshot `DS-SYNTH-001`:

- 28 subjects, 16 weeks, 884 CMJ trials, 397,150 force samples, 448 weekly load
  rows, 448 wellness rows, a 180 s match-tracking segment.
- Seed `20260924`, generator `dynamis-synthetic@1.0.0`.
- Checksums are exposed in the Today aside, the Data page and every generated
  report's provenance block.
- No squad workspace consumes the admitted real datasets.

### Research workspaces

The existing local research store and immutable artifacts remain authoritative:

- Real datasets: Mendeley/Holmberg sprint priming and MoveSmart wearable IMU.
- Synthetic study: STUDY-001.
- Existing projects, studies, monitoring programs, cohorts, frozen plans, runs,
  evidence, figures, lineage and scientific reports are unchanged.
- Real-data and synthetic-data studies remain visually and structurally separate.

### Operational state (not measurements)

The following state is created by the user and stored separately from the
snapshot under the configured data root (`<data-root>/performance/`):

| Object | Source label | Notes |
|---|---|---|
| Plan targets and published weeks | `BASELINE_DERIVED_TEMPLATE` | Planning template derived from observed rolling load; explicitly not a measurement. |
| Session logs | `COACH_ENTERED` | sRPE = duration × RPE; stored separately from immutable tables. |
| Athlete performance notes | `COACH_ENTERED` | Performance observations only; not clinical notes. |
| Reliability assessments | `COMPUTED` | Append-only computed record with snapshot checksum and algorithm version. |
| Performance reports | `dynamis-performance.report@1.0.0` | Versioned; freeze stores content hash and timestamp. |

### Honest absence

- The fixture has **no injury or exposure table**. Injury surveillance and injury
  burden are shown as unavailable, never estimated.
- Return-to-play is unavailable because no injury, criteria or clearance contract
  is admitted.
- Attendance and drill-level session planning are P2 and shown as unavailable.
- Persistent alert assignment/status/review lifecycle is P2; Today shows a
  threshold review list, not a simulated alert workflow.
- Bayesian hierarchical models and ML/PIML prediction are not implemented and
  are not shown as available.
- Sprint and strength testing batteries are unavailable for this squad; only CMJ
  force-plate testing is admitted.

## 3. Feature and availability matrix

Status vocabulary: **Implemented** = working interaction, persistence and
validation; **Unavailable** = explicit empty state, not simulated; **P2** =
deferred, visibly unavailable.

| # | Module | Status | Where | Notes |
|---:|---|---|---|---|
| 1 | Squad Command | Implemented (P0) | Today | Pulse, attention, readiness distribution, checklist, squad availability. |
| 2 | Athlete 360 | Implemented (P0) | Athlete | Header, status, readiness, load, CMJ, testing, movement, notes, research. |
| 3 | Wellness & Readiness | Implemented (P1) | Monitor, Athlete | Sleep, soreness, fatigue, readiness trends, distribution, missing state. |
| 4 | Training Load | Implemented (P1) | Monitor, Athlete, Plan | sRPE AU, external load, duration, HSR, match minutes, load ratio. |
| 5 | Session Planner | Implemented P1 scope; attendance P2 | Plan | Editable microcycle, groups, targets, testing window, publish, audit. |
| 6 | Testing Battery | Implemented (P1) | Test | Protocol, device caveat, trial quality, completion, trial register. |
| 7 | Force Lab | Implemented (P1) | Test, Today, Athlete | 1000 Hz force–time, phase shading, peak, impulse, RSI, trial quality. |
| 8 | Movement / GPS | Implemented bounded scope (P1) | Monitor, Athlete | 180 s segment, distance, HSR, max speed, position-reset warning. |
| 9 | Availability & Injury | Unavailable | Today, Monitor, Athlete, Report | No injury/exposure table; roster status only. |
| 10 | Return to Play | Unavailable (P2) | Monitor, Reports | No injury/criteria/clearance contract. |
| 11 | Periodization | Implemented (P1) | Plan | Four blocks, match weeks, testing windows, actual/reference load. |
| 12 | Alerts & Triage | Threshold review implemented; alert lifecycle P2 | Today, Atlas | Owners, dates and thresholds shown; no simulated alert status. |
| 13 | Data Quality | Implemented | Today, Monitor, Test, Data | Valid/excluded/missing, checksums, trial quality, provenance. |
| 14 | Research & Evidence | Implemented | Research, workbench | Projects, studies, cohorts, plans, runs, evidence, model lab, decision brief. |
| 15 | Reports | Implemented (P1) | Report | Athlete/coach/medical/board templates, versions, freeze, HTML export. |
| 16 | Settings / Units | Implemented as Atlas + role selector | Atlas, topbar | 24 canonical units, thresholds, status atoms, design rules, role-aware nav. |

### Deferred P2 capabilities, explicitly unavailable

- Injury surveillance, exposure denominators and injury incidence.
- Return-to-play criteria and clearance.
- Attendance, drills and session-level roster assignment.
- Persistent alert rules with assignment, acknowledgement and review timestamps.
- Power/sample-size and sensitivity workflows.
- Bayesian hierarchical and ML/PIML prediction.

## 4. Units, thresholds and status language

The Atlas (`/atlas`) is backed by `/performance/units` and renders 24 canonical
quantities, including cm, m, s, N, N·kg⁻¹, N·s·kg⁻¹, W·kg⁻¹, m·s⁻¹, m·s⁻²,
AU, RPE, 0–10, h, kg, %, ICC, TE, SD, per 1000 h, and min.

Defaults and provenance:

| Rule | Threshold | Owner | Set |
|---|---|---|---|
| Readiness low | below 5.5 /10 | Head of Performance | 2026-11-05 |
| Load ratio high | above 1.30 AU | Head of Performance | 2026-11-05 |
| CMJ below baseline | below −2.5% | Sports Scientist | 2026-11-05 |
| Soreness high | above 7.0 /10 | Head of Performance | 2026-11-05 |

Design rules are enforced or explicitly surfaced:

- No value without a unit.
- No chart without a reference window.
- Missing is visible and never zero-filled.
- Planned and actual are separate.
- No ACWR-as-injury-prediction claim.
- No causal language from observational data.
- Every exception has a next action/owner.

## 5. Architecture

### Backend

New `services/science/dynamis_science/performance.py` composes the six workspaces
from the immutable snapshot and existing scientific store. It adds `/performance/*`
endpoints without changing existing analysis, evidence or report contracts:

- `GET /performance/context`, `/today`, `/athletes`, `/squad-weeks`,
  `/athletes/{id}`, `/load`, `/plan`, `/tests`, `/movement`, `/units`,
  `/research`, `/reports`.
- `POST /performance/sessions`, `/athletes/{id}/notes`,
  `/tests/reliability`, `/reports`, `/reports/{id}/freeze`.
- `PUT /performance/plan`, `POST /performance/plan/publish`.
- `GET /performance/reports/{id}/export` (HTML).

The router is included by `api.py`; the existing `api.py` computation paths are
unchanged except for the import/include.

### Frontend

- `app/layout.tsx` + `app/performance.css` — Direction F shell, tokens and
  responsive breakpoints.
- `components/shell/PerformanceBar.tsx`, `PerformanceRail.tsx`,
  `RoleContext.tsx`, `CommandPalette.tsx` — shared chrome, search and role model.
- `components/performance/TodayView.tsx` — Squad Command.
- `components/performance/AthleteView.tsx` — Athlete 360.
- `components/performance/PlanView.tsx` — periodization and microcycle planner.
- `components/performance/MonitorView.tsx` — longitudinal monitoring and movement.
- `components/performance/TestView.tsx` — battery, reliability and force lab.
- `components/performance/ResearchWorkspaceView.tsx` — research entry and model lab.
- `components/performance/ReportsView.tsx` — audience templates and versions.
- `components/performance/AtlasView.tsx` — component/unit/status atlas.
- `components/performance/charts.tsx` — responsive SVG charts with hover,
  references, missing gaps, phase shading and heatmap.
- `lib/performance/*` — typed API client, domain types, formatting and units.

Existing `/research/studies/[studyId]` and `/research/projects/[projectId]`
continue to use the scientific workbench. The workbench defaults its inspector
closed at narrower desktop widths so the Performance OS rail does not crowd the
investigation; the existing toggle remains fully functional.

## 6. Validation

### Automated checks

Commands were run from the repository root or `apps/web`:

| Check | Command | Result |
|---|---|---|
| Python science suite | `uv run --directory services/science pytest -q` | **84 passed** |
| Performance OS suite | `uv run --directory services/science pytest -q tests/test_performance.py` | **11 passed** |
| Web unit/component tests | `node node_modules/vitest/vitest.mjs run` | **35 passed** |
| TypeScript | `node node_modules/typescript/bin/tsc --noEmit` | **clean** |
| ESLint | `node node_modules/eslint/bin/eslint.js .` | **clean** |
| Production build | `node node_modules/next/dist/bin/next build` | **success** |
| Browser validation | `uv run --directory services/science python ../../scripts/res588_performance_validate.py` | **pass** |

Browser validation ran against the production build and the live local science
service at `1440×900`, `1280×800` and `1024×800`:

- No console errors.
- No horizontal page overflow at any required viewport.
- All required screenshots captured.
- Both operational workflows completed.
- Role-aware navigation and medical report default verified.
- Data-honesty statements present (injury unavailable, roster-only,
  bounded GPS, threshold owner, unit registry, no fabricated injury rate).

The machine-readable receipt is
`docs/design/res588-ux/implemented/validation-receipt.json`.

### Workflow 1 — Today → Athlete 360 → Monitor → Test → Research → Evidence → Report

1. `/today` → attention row `ATH-003` → `/athletes/ATH-003`.
2. Athlete 360 → **Monitor trajectory** → `/monitor?athlete=ATH-003`.
3. Monitor → **Test** → **Run reliability check** → computed assessment saved.
4. Test → **Research** → **Evidence ledger** → first evidence item opens the
   study workbench with the evidence inspector.
5. Research → **Reports** → **Compose coach report** → preview → **Freeze** →
   version/hash recorded; HTML export available.

### Workflow 2 — Plan → Training Load → Monitoring → Testing → Report

1. `/plan` → edit W17 planned load → **Publish week** → reload → persisted value.
2. Plan → **Open training load** → `/monitor?metric=load`.
3. Monitor → **Test** → battery, force lab, reliability.
4. Test → **Reports** → coach/medical/board report preview and version history.

### Visual comparison

- Approved Squad Command: `docs/design/res588-ux/screens/f-command-1440x900.png`.
- Implemented Squad Command: `docs/design/res588-ux/implemented/today-1440.png`.
- Approved Component atlas: `docs/design/res588-ux/screens/f-atlas-1440x900.png`.
- Implemented atlas: `docs/design/res588-ux/implemented/atlas-1440.png`.

The implemented screens use the same navy panel surface, lime/cyan signal system,
mono metadata, rail cadence, pulse strip, attention rows, force–time chart,
research cards, right-rail honesty callouts, compact breakpoints and 300 px
context rail. Actual computed values replace prototype values; where the
fixture differs (for example ATH-014 versus ATH-002 as the fifth CMJ drop), the
computed value is retained rather than copied from the exemplar.

### Screenshot index

`docs/design/res588-ux/implemented/` contains:

- `today-1440.png`, `today-1280.png`, `today-1024.png`
- `plan-*.png`, `monitor-*.png`, `test-*.png`, `research-*.png`,
  `report-*.png`, `atlas-*.png`, `athlete-*.png`
- `workflow-athlete-1440.png`, `workflow-test-1440.png`,
  `workflow-evidence-1440.png`, `workflow-evidence-workbench-1440.png`,
  `workflow-model-lab-1440.png`, `workflow-report-1440.png`,
  `workflow-plan-published-1440.png`, `workflow-role-medical-1440.png`
- `scientific-report-1440.png`
- `comparison-command-2880.png`, `comparison-atlas-2880.png`
- `comparison-command.html`, `comparison-atlas.html`
- `validation-receipt.json`

## 7. Known limitations

1. All squad performance values are synthetic. They are suitable for product and
   workflow validation, not for external scientific or clinical claims.
2. Device serial, calibration date and plate coverage are not admitted; the CMJ
   device is explicitly a fixture.
3. The match-tracking segment contains two positional resets. Distance is
   positional path length and is not a full-match distance or a GPS validation.
4. Roster-to-tracking-channel mapping is not admitted, so Athlete 360 does not
   claim a specific athlete is PLAYER-14.
5. Injury, exposure, return-to-play, attendance and persistent alert lifecycle
   require new P2 data contracts and are shown as unavailable.
6. Research reliability is within-session trial agreement, not device agreement.
7. The training-response model is a local prototype. Its scenario output is
   explicitly model-generated and is not a performance or injury prediction.
8. Linear was not updated from this environment because no Linear credentials or
   MCP connection were available. A ready-to-paste update is in
   `docs/RES-588_LINEAR_UPDATE.md`.

## 8. RES-588 acceptance matrix

| Requirement | Evidence | Status |
|---|---|---|
| Six integrated workspaces Today/Plan/Monitor/Test/Research/Report | Routes and screenshots at three viewports | Met |
| P0 daily credibility | Squad Command, Athlete 360, status language, data-quality empty states, role-aware nav | Met |
| P1 weekly practice | Wellness, training load, testing, periodization, movement, coach/medical/board reports | Met |
| Approved prototype fidelity | Today/Atlas side-by-side evidence; shared component/unit system | Met |
| Preserve scientific infrastructure | Existing 84-test science suite passes; workbench/evidence/report routes still live | Met |
| Real computed data | `/performance/today` values equal fixture aggregates; report provenance cites DS-SYNTH-001 | Met |
| Deterministic labelled fixtures | Plan template and user-entered operational logs labelled separately | Met |
| No fabricated measurements/injury/results/predictions | Explicit unavailable states; no injury rate; model scenarios labelled | Met |
| Real interactions, persistence, filtering, athlete selection, longitudinal exploration, testing, navigation | Both browser workflows and validation receipt | Met |
| P2 unavailable rather than pretended | Injury/RTP/attendance/alert lifecycle/Bayesian/ML states | Met |
| Scientific/backend/frontend regression tests, lint, typecheck, build | 84 Python + 35 web tests, clean lint/typecheck, successful build | Met |
| Browser validation at 1440×900, 1280×800, 1024×800 | `validation-receipt.json`; 24 screenshots | Met |
| Local commits, no push | See final Git status and commit list | Met |
| Linear update with verified evidence | No Linear access in environment; update draft supplied | Blocked by credentials |
| Final product acceptance | Owner review | Pending |

## 9. Commits

Local, unpushed implementation commits:

- `103e8cc` — compose Performance OS workspaces from admitted snapshot.
- `6863160` — implement six workspaces and component atlas.
- `f23a1e7` — record validation, screenshots and acceptance matrix.

## 10. Run locally

```powershell
$env:DYNAMISSCIENCE_DATA_ROOT = Join-Path $env:LOCALAPPDATA 'DynamisScience'
$env:DYNAMISSCIENCE_PERFORMANCE_STORE = Join-Path $env:DYNAMISSCIENCE_DATA_ROOT 'performance'

# Terminal 1 — science service
uv run --directory services/science uvicorn dynamis_science.api:app --port 8000

# Terminal 2 — web
cd apps/web
node node_modules/next/dist/bin/next dev -p 3000
```

Open `http://localhost:3000/today`.

Production:

```powershell
cd apps/web
node node_modules/next/dist/bin/next build
node node_modules/next/dist/bin/next start -p 3000
```

Validation:

```powershell
uv run --directory services/science python ../../scripts/res588_performance_validate.py
```
