# RES-620 — Design exploration: a research-oriented sports-science workstation

**Status:** exploration only, awaiting the owner's choice of direction. Nothing in this document is implemented.
**Date:** 2026-11-10
**Prototypes:** [`res620-prototypes/index.html`](res620-prototypes/index.html). These are static HTML pictures of *native Qt Widgets windows*. They only show layout and hierarchy. They are not a web product, and they do not propose any web runtime.
**Inputs:** RES-620 scope, RES-613 findings ([RES-613_ACCEPTANCE.md](RES-613_ACCEPTANCE.md)), RES-619 round-3 method states, the as-built shell (`desktop/main_window.py`, `desktop/performance_workbench.py`, `desktop/theme.py`) and the earlier web-era exploration ([`docs/design/res588-ux`](../design/res588-ux/RES-588_UX_AUDIT_AND_DIRECTIONS.md)).

The numbers in the prototypes come from RES-619 receipts. Examples: `RUN-REAL-0005` slope 0.998 cm/occasion (Wald 0.622–1.375), and `RUN-REAL-0004` ICC(3,1) 0.889 (0.745–0.969), TE 75.78 N, MDC95 210.05 N. The plotted points are illustrative shapes, and every prototype screen says so.

---

## 1. Design brief

**What DynamisScience is:** a native Windows workstation where a sports scientist goes from a research question to a defensible, provenance-carrying result. The steps are: question → admitted dataset snapshot → cohort → frozen analysis plan → immutable run → diagnostics → interpretation and limitations → promoted evidence → versioned report.

**What it is not:**
- It is not a monitoring dashboard. Wall-of-tiles readiness views are a secondary workflow.
- It is not a notebook or general-purpose IDE. Users do not write code to get a qualified result.
- It is not a simulator. Scenario and what-if work is a later, clearly fenced capability (RES-590).
- It is not a web app. Qt Widgets, SQLite, Parquet, Matplotlib and pyqtgraph stay authoritative.

**The rule every direction must keep: three kinds of claim, never blended.**

| Kind | What it is | Visual treatment (all directions) | Existing source |
|---|---|---|---|
| **Observed** | Measured values from an admitted snapshot | Solid marks, neutral text, the "OBS" chip | `DatasetSnapshot`, Parquet tables |
| **Modeled** | Estimates with uncertainty from a run | Estimate ± interval always shown together, blue, the "MOD" chip, method status beside it | `AnalysisRun`, `EvidenceArtifact` |
| **Hypothetical** | Scenario or simulation output | Hatched fill, amber, the "HYP" chip, never mixed into the same axes as observed data unless overlaid and labelled | fitness–fatigue prototype; future RES-590 |

Two more axes are shown *separately* from the kind of claim, because each is a different question:
- **Provenance:** REAL or SYNTHETIC. This answers where the data came from. A synthetic observation is still observed. It is just not empirical.
- **Method status:** QUALIFIED, DESCRIPTIVE, EXPLORATORY, UNAVAILABLE or SUPERSEDED (RES-619). This answers how far a modeled result may be trusted.

## 2. Users and workflows

| Journey | User | Steps | Frequency |
|---|---|---|---|
| **Scientific research** (primary) | Sports scientist or researcher | Define the question and protocol → choose the snapshot and check its rights → define the cohort and exclusions → specify the model (outcome, fixed effects, grouping, contrasts) → freeze the plan → run → review diagnostics and assumptions → write the interpretation and limitations → promote the evidence → cite it in a report → freeze and export | Days to weeks per study, with many runs |
| **Applied performance** (secondary) | Practitioner or performance staff | Today context → athlete or session → test (for example CMJ) → compare against typical error or MDC → note → practitioner report | Daily |
| **Scenario or simulation** (future) | Researcher | Fork from a qualified model → set assumptions → run the scenario → compare it with the observed and modeled baseline → export it labelled HYPOTHETICAL | Occasional. Gated by RES-590. |

## 3. Reference patterns (influences, not copies)

These come from general knowledge of each software category. They were not taken from a hands-on audit of any one product.

| Category | Pattern taken | Where it lands |
|---|---|---|
| Statistical analysis software (RStudio, jamovi, JASP, SPSS, Prism, Minitab) | A variable list on the left with **role slots** (Outcome / Fixed / Grouping / Random). An **output tree** per run (Tables → Figures → Diagnostics → Notes). Assumption checks listed beside the result. A Prism-style project where data, analyses, graphs and layouts are linked and marked **stale** when an upstream item changes. Export figures with captions. | Model setup, run output tree, diagnostics, lineage "stale" state |
| Scientific computing (MATLAB, Mathematica-style, Origin-like) | A workspace or **object browser** of typed computational objects. **Run history** as a first-class list. Templates for reusable analyses. **Branch or fork** an analysis without losing the parent. Dockable, saveable layouts. | Project explorer, run history dock, "fork plan" action, `QMainWindow.saveState()` layouts |
| Sports-science and athlete-performance tools | **Athlete / session / test context bar**. Roster-first daily view. Test-capture flow (test type → athlete → trials → metrics). Change shown against a noise threshold (TE or MDC) instead of colour-only traffic lights. Short practitioner reports. | Performance OS perspective, athlete context bar, change-vs-MDC display |

Patterns deliberately rejected: free-form notebooks (already rejected as RES-588 option B), unlabelled red/amber/green readiness lights, and browser-style tabs or routing.

## 4. Information architecture

The object model already exists in `contracts.py`. The navigation should show it, not invent a new one:

```
Project
└─ Study (question, protocol, status)
   ├─ Datasets         (snapshots · rights · provenance REAL/SYNTHETIC)
   ├─ Cohorts          (versioned)
   ├─ Analysis plans   (draft → frozen → forked)
   │  └─ Runs          (immutable · method status)
   │     └─ Outputs    (tables · figures · diagnostics)
   ├─ Evidence         (promoted from runs · CURRENT/SUPERSEDED)
   ├─ Reports          (versions · draft/frozen)
   └─ Scenarios        (future · HYPOTHETICAL only)
Performance OS (separate perspective): Today · Athlete 360 · Plan · Monitor · Test · Match & Pose · Research · Report
```

Shell elements shared by all three directions: a `QMainWindow` with a menu bar, docks restored through `QSettings`, a status bar that always shows the data root, the provenance and the selection, a structured `QTreeView` inspector instead of the raw-JSON `QTextBrowser` (RES-613 finding), and a raw-detail view reached only through *View ▸ Advanced*.

## 5. Three directions

### A — Scientific IDE

- **Philosophy:** everything is an object in a dense, dockable workspace. Expert speed comes first. Influences: RStudio, MATLAB and Origin.
- **Target user:** a methodologist who runs many models and compares runs side by side.
- **Screen hierarchy:** project explorer dock (left) · tabbed documents in the centre (plan, run, figure, report; several open at once) · properties inspector (right) · bottom dock with **Output tree / Run history / Log**.
- **Modeling:** a plan document with a variable list and role slots, specification diff against the previous frozen version, and a freeze button.
- **Diagnostics:** a run document has a Diagnostics tab with a 2×2 plot grid and an assumption table. The exploratory Q–Q is labelled exactly as RES-619 defines it.
- **Evidence and reporting:** "Promote" from the output tree. The report is a document tab with citation chips that link back to evidence.
- **Performance OS:** a separate saved dock layout (perspective) switched from the toolbar.
- **Simulation later:** a "Scenario" object type in the explorer, opened in a document tab with a hatched HYP frame.
- **Strengths:** highest density, best comparison of runs, and the closest fit to the current dock-based shell.
- **Trade-offs:** steepest learning curve. The lifecycle order is implicit, so a user can skip diagnostics. It is crowded at 1366×768.

### B — Guided Research Studio

- **Philosophy:** the research lifecycle is the navigation. Each stage is one focused page with an exit checklist. Influences: jamovi/JASP clarity and Prism's guided flow.
- **Target user:** an applied scientist or graduate researcher who runs fewer, careful studies.
- **Screen hierarchy:** study browser (start screen) → a **stage rail** on the left: 1 Design · 2 Data · 3 Cohort · 4 Model · 5 Diagnostics · 6 Interpret · 7 Evidence · 8 Report · (Scenarios, locked) → one stage page in the centre → a "Ready to continue?" checklist panel on the right.
- **Modeling:** a role-slot form with a plain-language model summary ("CMJ height ~ occasion + (1 | athlete)").
- **Diagnostics:** a mandatory stage. Each assumption has a state (checked, exploratory or unavailable) and a required acknowledgement before evidence can be promoted.
- **Evidence and reporting:** promotion requires written limitations. The report stage is a structured outline built from promoted evidence.
- **Performance OS:** a separate top-level mode reached from the study browser.
- **Simulation later:** an extra rail stage after Report, locked until a qualified model exists.
- **Strengths:** easiest to learn, the clearest scientific order, and it enforces diagnostics and limitations.
- **Trade-offs:** slower for experts and weak at comparing runs. Rigid when the work is iterative.

### C — Dual-Mode Performance Laboratory

- **Philosophy:** one product with two equal rooms, a Research Lab and a Performance Floor, plus a fenced Scenario Bench. Influences: sports-performance and testing tools combined with an analysis package.
- **Target user:** an embedded club scientist who does both daily support and research.
- **Screen hierarchy:** mode switcher at the top (Research Lab · Performance Floor · Scenario Bench) · athlete/session context bar · room-specific panels.
- **Modeling:** inside the Research Lab, on panels styled like instruments (setup | result | diagnostics side by side).
- **Diagnostics:** a panel in the Lab, which is less prominent than in B.
- **Evidence and reporting:** a shared "Evidence shelf" visible from both rooms. Practitioner reports and research reports are separate.
- **Performance OS:** a full peer of research. Today and Athlete 360 come first.
- **Simulation later:** the Scenario Bench is already a room. It is hatched, amber and watermarked HYPOTHETICAL.
- **Strengths:** best for practitioners, the strongest athlete context, and simulation already has a home.
- **Trade-offs:** it pulls the product toward monitoring, against the stated primary purpose. The Scenario room invites premature simulation UX. It is the largest Qt surface to maintain.

### D — Evidence Sheet (open brief, the designer's own proposal)

- **Philosophy:** a study is a **question**, and the main screen is its **written answer**. The headline is one sentence with the estimate and its interval, set in a serif like a journal abstract. Everything below it explains why that sentence can be trusted. Objects, stages and rooms stay in the background.
- **Target user:** both the methodologist and the applied scientist. The answer is readable at a glance, and every step behind it is one click away.
- **Screen hierarchy:** a slim dark global rail (Questions · Datasets · Athletes · Reports · locked Scenarios) · a question list showing each question's progress · the answer canvas with Answer / Model / Checks / Report views · a "Why trust this answer?" panel · a **run timeline** strip along the bottom that shows forks and superseded runs.
- **Modeling:** a **sentence composer**. The user writes "Explain *cmj_height* by *occasion*, with each *athlete* keeping their own baseline. Compare *Pre* with *Post 24h*." The workstation picks the qualified method, writes the formula, and shows the athlete × occasion map with missing cells marked before anything runs.
- **Diagnostics:** an **assurance strip** under the answer shows Data · Rights · Method · Checks · Limitations, with progress for each. Open checks link to the Checks view, where each check is a card with a verdict and an "acknowledge as limitation" action.
- **Evidence and reporting:** an **evidence ladder** (data → cohort → frozen plan → run → checks → evidence) sits on the answer itself. The report is the same sheet laid out as a paper page, with a FROZEN stamp and its hash.
- **Performance OS:** an athlete page with the same answer-first pattern ("A07 is +242 N above baseline: beyond the ±210 N noise band"). It shows a change-vs-MDC chart and observed context, never a readiness score.
- **Simulation later:** a locked rail item. When unlocked, scenarios get the same sheet format with an ochre, hatched HYPOTHETICAL headline.
- **Strengths:** the clearest communication of results, scientific honesty built into the layout (interval in the headline, trust strip, no-threshold notice), a visible history of runs, and sports context (every athlete at a glance).
- **Trade-offs:** the most new composition work of the four (sentence composer, small multiples, timeline). Comparing runs side by side needs a separate compare view. The answer-first framing has to stay honest when a result is null or inconclusive.

### E — Analysis Workbench (familiar statistical software, crafted)

- **Philosophy:** add no new mental model. Scientists already know the three-pane statistics layout of JASP, jamovi and SPSS: **data grid | analysis options | results**. E uses it as-is and puts the quality into the details. Owner feedback (2026-11-10) asked for software that feels like real data-science and statistical-modeling tools, without drift or cognitive overload.
- **Target user:** statisticians, sports scientists and data scientists who expect to be productive in the first minute.
- **Screen hierarchy:** menu bar · an **analysis ribbon** (Descriptives, T-Tests, ANOVA, Regression, Mixed Models, Reliability, Frequencies | Signals, Athlete change) · data grid · analysis options · results document · a **syntax line** that shows the equivalent Python call for every analysis.
- **Data:** a spreadsheet grid. Each column header shows the variable type icon, its unit and role, a mini distribution, a missing-data bar and a one-line summary. The dependent variable is underlined in the modeled colour. The grid follows the dataset of the active analysis.
- **Modeling:** the familiar variable-assignment boxes (Dependent / Covariates / Factors / Cluster) with collapsible option sections (Model, Assumption checks, Plots, Marginal means, Save). Results update when options change ("Results up to date").
- **Diagnostics:** assumption checks are checkboxes in the options pane and appear in the results with their RES-619 labels (CONDITIONAL, EXPLORATORY, N/A).
- **Evidence and reporting:** results are publication-style tables (model information, fixed effects with CI) with an honest note. Each block has a provenance footer (method status · run · digest) and a **Promote to evidence** action. "Add to report" collects blocks into a report.
- **Performance OS:** appears as ordinary analyses in the ribbon (Athlete change, Signals), so there is no second product to learn.
- **Simulation later:** a ribbon group added only after RES-590. Its results blocks carry the HYP chip and hatched figures.
- **Themes:** "Paper & Ink" light and a warm-graphite dark theme, both defined as Qt palette and stylesheet tokens.
- **Strengths:** near-zero learning cost for the target users, the closest match to existing statistical software, and syntax that makes every GUI action reproducible. Straightforward in Qt: `QTableView` with a custom header delegate, `QListView` assignment boxes, a `QTextBrowser` or widget results document, and a `QDockWidget` per pane.
- **Trade-offs:** project-level navigation (studies, evidence, reports) lives in menus and the results outline rather than being always visible. The column-header summaries need a custom `QHeaderView` paint.

### E — interaction specification (owner-selected direction, 2026-11-10)

The owner chose E ("This is it") and asked for it to be interactive, intuitive and 3D. The prototype at port 8605 now behaves as the app should. Each behaviour below has a native Qt equivalent:

| Behaviour | Prototype | Native Qt equivalent |
|---|---|---|
| Assign variables | Drag a variable to a box, or click it then click the box. Double-click auto-assigns by type. ✕ removes it. | `QListView` + `QAbstractItemModel` drag and drop (`mimeData`), custom role boxes |
| Validation | Invalid drops are refused with a shake and a plain reason ("The cluster must be an identifier…"). | Model `canDropMimeData` + a status-bar or `QToolTip` message |
| Live syntax | The Python call and formula rewrite on every change. | Spec → syntax generator, with the run itself still done by the qualified worker |
| Stale results | Changing the spec greys out the results under a "Specification changed · Run (Ctrl ↵)" bar. Run executes. Restore brings back the recorded spec. | Spec hash compared with the run's spec. `QGraphicsOpacityEffect` on result widgets. `TaskRunner` for the run |
| Option sections | Collapsible sections. Checkboxes add or remove result blocks instantly. Unavailable options are disabled with a reason. | `QToolBox` or custom collapsible `QGroupBox`es, bound to result widgets |
| Column focus | Clicking a column header highlights the column and its variable. | `QHeaderView.sectionClicked` + selection model |
| Resizable panes | Drag the gutters between the three panes. | `QSplitter`, with state saved in `QSettings` |
| Command palette | Ctrl K: analyses, variable assignments (only valid ones), checks, theme, run. ↑↓ ↵ Esc. | Frameless `QDialog` + `QLineEdit` + filtered `QListView` |
| Outline | Jump to any result block. | `QMenu` built from result sections |
| Provenance actions | "Promote to evidence" on each block, reporting honestly if it is already promoted. | Existing promotion service |
| **3D trajectories** | Rotate by dragging, zoom with the wheel, hover to see athlete · occasion · value. Layers: observed points, model surface, athlete lines. Front, Side and 3D presets. | `pyqtgraph.opengl` (`GLViewWidget`, `GLScatterPlotItem`, `GLMeshItem`), which the app already depends on through pyqtgraph |
| Depth | Panes are raised cards on a darker desk. Tactile ribbon buttons and soft elevation on result blocks. | Stylesheet borders and radii, plus `QGraphicsDropShadowEffect` used sparingly |
| Themes | Light "Paper & Ink" and warm-graphite dark. | `QPalette` + one stylesheet per theme |

**Data pane (owner feedback: the long athlete_id/occasion table was confusing).** The default is now **By athlete**: one row per athlete, occasions as columns, a Δ 24 h column, a trend sparkline and missing jumps marked. **Variables** lists each variable with a plain label, type, role, distribution and missing data. **Rows** keeps the raw long table for anyone who needs it. Native: a `QTableView` over a pivot proxy model, with a delegate for sparklines.

**Every ribbon analysis now has a working screen:**

| Analysis | Options | Results | Status label |
|---|---|---|---|
| Descriptives | Variables, Split by; N/missing, mean/SD, median/IQR, min/max, 95% CI; box plot, histogram | Table + box plot with points | DESCRIPTIVE |
| Paired T-Test | Outcome, Paired by, Subject; choose any two occasions; mean difference + CI, d<sub>z</sub>, descriptives | Test table + a line per athlete | NOT QUALIFIED |
| Repeated-measures ANOVA | Outcome, repeated factor, Subject; partial η², Holm post hoc, means plot; sphericity marked N/A | Within-subject table, post hoc table, means ± CI | NOT QUALIFIED |
| Linear Regression | Dependent, Covariates; CI, standardised estimates, fit, scatter, residuals | Coefficients, fit, scatter with CI band; warns when repeated rows make the SEs too small | NOT QUALIFIED |
| Mixed Models | (as above) | Recorded run RUN-REAL-0005 | QUALIFIED |
| Reliability | (as above) | Recorded run RUN-REAL-0004 | QUALIFIED |
| Frequencies | Categorical variables; bar chart | Counts, %, cumulative %, missing outcome per level | DESCRIPTIVE |
| Athlete change | Outcome, occasion, athlete; from/to; optional smallest worthwhile change | Diverging bars + per-athlete table; says when no qualified threshold exists | OBSERVED CHANGE |
| Signals | n/a | Explains that trace derivation needs the MoveSmart traces; screen not drawn | QUALIFIED |

The analyses without a recorded run compute live in the prototype from illustrative values, and every result block is labelled ILLUSTRATIVE DATA. In the app they would run in the worker. Methods outside the qualified catalogue are labelled NOT QUALIFIED, and their promotion to evidence is disabled.

Renders: `E4` mixed model · `E5` 3D (dark) · `E6` stale specification · `E7` command palette (dark) · `E8` descriptives · `E9` paired t-test (dark) · `E10` RM ANOVA · `E11` regression with the Variables view · `E12` athlete change (dark) · `E13` reliability.

## 6. Key screens per direction

| Screen | A — Scientific IDE | B — Guided Research Studio | C — Performance Laboratory |
|---|---|---|---|
| Project/study browser | Explorer dock tree with status columns | Full-page study cards: question, stage reached, last frozen report | Lab lobby with recent studies next to today's squad summary |
| Dataset/cohort | Snapshot document: schema table, Parquet preview, rights panel; the cohort as a filter document | Stages 2 and 3: snapshot picker with rights and provenance check, then an inclusion/exclusion builder with live N | Lab "Data bench" panel, with the athlete roster as cohort source |
| Model setup | Variable list + role slots + spec diff + freeze | Role-slot form + plain-language formula + "freeze plan" gate | Setup instrument panel next to a live result panel |
| Diagnostics | Run tab: 2×2 plots + assumption table + output tree | Stage 5: assumptions one by one with required acknowledgement | Diagnostics instrument panel (compact) |
| Evidence/provenance | Lineage graph in a document tab and promotion from the output tree | Stage 7: evidence card with limitations, then the lineage strip | Evidence shelf drawer shared by both rooms |
| Reporting/export | Report document with citation chips; export PNG/PDF/SVG/HTML | Stage 8: outline built from evidence, freeze and export | Two report types: practitioner and research |

Direction D, screen by screen: the **question list** is the study browser. **Model** combines the sentence composer, the method choice and the athlete × occasion data map. **Checks** shows verdict cards. The **answer sheet** carries the evidence ladder and the trust panel. The **report** is the paper page with a frozen stamp. There is also an **athlete** page.

The prototypes draw the model-setup, diagnostics and evidence screens in full for each direction. Rendered images are in [`res620-prototypes/renders/`](res620-prototypes/renders) (A1–A4, B1–B4, C1–C3, D1–D5, E4–E13). The palette is "Paper & Ink": warm paper surfaces, a pine accent, graphite for observed data, cobalt for modeled values and hatched ochre for hypothetical ones. The other screens appear in the navigation as labelled placeholders.

## 7. Evaluation matrix

These ratings are design judgments made against this brief. They are **not** measured usability scores. No user testing has been done.

| Criterion | A — IDE | B — Guided Studio | C — Perf. Lab |
|---|---|---|---|
| Scientific clarity (order, claim types) | Medium: order is implicit | **High**: order is the navigation | Medium: two rooms compete |
| Support for statistical modeling | **High** | High | Medium |
| Support for diagnostics | High: dense, but skippable | **High**: enforced | Low–Medium |
| Support for reporting | High | **High** | Medium: split in two |
| Ease of learning | Low | **High** | Medium |
| Density vs usability at 1366×768 | Low: four docks crowd | **High**: one page at a time | Medium |
| Qt feasibility on the current shell | **High**: docks and tabs exist | High: rail = `QListView` + `QStackedWidget`; the 5 tabs map to stages | Medium: three shells to restyle |
| Long-term extensibility | **High**: new object types | Medium: new stages are cheap, but there is no side-by-side view | Medium: rooms multiply |
| Fit to "modeling first, simulation later" | High | **High** | Low |

**Direction D against the same criteria (design judgment):** scientific clarity high (the interval is in the headline) · modeling high · diagnostics high (the assurance strip cannot be missed, though acknowledgement is not enforced as hard as in B) · reporting the highest (the sheet becomes the report) · ease of learning high · density at 1366×768 medium (the trust panel can collapse) · Qt feasibility medium (`QTextBrowser` or `QLabel` serif headline, a custom-painted strip and timeline, a small-multiples grid of pyqtgraph `PlotWidget`s) · extensibility high · simulation fit high (locked, then same sheet with a HYP headline).

## 8. Recommendation

**A hybrid: B's lifecycle spine on A's dock shell. Performance OS stays a separate perspective, and scenarios stay locked.**

- B gives the research order, enforced diagnostics and limitations, and the best behaviour at 1366×768. These are the RES-613 and RES-619 pain points.
- A supplies what B lacks for real research work: an output tree, run history, and side-by-side run comparison as an optional bottom dock and a second document. The current `QMainWindow` with its navigator and inspector docks already is this shell, so the risk is low.
- C's athlete context bar and change-vs-MDC display are adopted inside Performance OS only. Its dual-room structure and Scenario room are rejected for now. They would push the product toward monitoring and simulation before the modeling core is accepted.

This is a recommendation. The owner chooses after viewing the three prototypes, and then the chosen direction is frozen as SVG screen specifications.

## 9. Next implementation plan (after approval)

Each step is a separately validated `RES-620` commit with offscreen Qt tests, the full science suite and installed-app screenshots at 1366×768 at 100% and 150%.

1. **Freeze the design as SVG specs:** the shell, the six screens, the component sheet (claim-kind chips, provenance, method status, tables, empty/loading/error states), and tokens. Stored under `docs/desktop/res620-design/`. No code yet.
2. **Tokens and component inventory in `theme.py`:** spacing, type scale, status colours with contrast checks, and named objects for the chips. One stylesheet replaces the per-widget `setStyleSheet` calls.
3. **Structured inspector:** replace the raw-JSON `QTextBrowser` with a `QTreeView` property model, and move raw detail to *View ▸ Advanced*.
4. **Lifecycle spine:** the five `ResearchWorkbench` tabs become the stage rail (`QListView` + the existing `QStackedWidget`), with exit checklists from existing state (frozen plan, run status, acknowledged diagnostics). No change to methodology.
5. **Run output tree and diagnostics stage:** a bottom dock with output tree and run history. The diagnostics page shows exactly the RES-619 labels and limitations.
6. **Evidence and report stages:** promotion with limitations, citation chips, and the frozen and superseded banners. Coordinate with RES-621.
7. **Performance OS perspective:** the athlete context bar and change-vs-MDC display. Separate saved layout.
8. **DPI and accessibility pass:** accessible names, focus order, contrast, and 1366×768 at 100% and 150%. Multi-monitor checks are marked untested where no hardware is available.

Scenarios stay a locked placeholder until RES-590 delivers a qualified model.

## 10. Owner decision (2026-11-10)

The owner chose **direction E, Analysis Workbench**, over A–D and the A/B hybrid, because it matches the software scientists already use and avoids new concepts. E was then made interactive and completed with all nine analysis screens and the by-athlete data pane, and frozen as specification **E 1.0** in [`res620-design/`](res620-design/README.md). That folder holds tokens, components, layout, the annotated main screen, the screen index, interaction flows, the Qt implementation map and the step-by-step plan. Directions A–D remain in this document as the explored alternatives.
