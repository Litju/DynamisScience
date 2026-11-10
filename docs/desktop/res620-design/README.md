# RES-620 · Design E "Analysis Workbench" · frozen specification E 1.0

**Decision:** the owner selected direction E on 2026-11-10 ("This is it", then "Yes, freeze E"). This folder is the frozen design basis for the native PySide6 implementation under RES-620. Nothing here is implemented yet.

**Live reference prototype:** `../res620-prototypes/e-workbench/` (serve with the `res620-e-workbench` entry in `.claude/launch.json`, port 8605). The prototype is a picture of a native Qt window, not a web product.

## Sheets

| File | Contents |
|---|---|
| [01-tokens.svg](01-tokens.svg) | Light "Paper & Ink" and dark "Warm graphite" colour tokens with Qt roles; type scale; spacing; radii; elevation |
| [02-components.svg](02-components.svg) | Chips on four separate axes, buttons, ribbon states, checkboxes, run-state pill, variable assignment states, by-athlete grid row, result block, stale bar, toast, command palette, figure marks |
| [03-layout.svg](03-layout.svg) | Window anatomy at 1440 × 900, pane sizes and minimums, 1366 × 768 rules, keyboard focus model |
| [04-main-annotated.svg](04-main-annotated.svg) | The main screen with 16 numbered specification callouts |
| [05-screens.svg](05-screens.svg) | All ten frozen screens (renders E4–E13) |
| [06-interactions.svg](06-interactions.svg) | Assignment → validation → live or stale → run → result → checks → promotion → report; keyboard map; 3D controls; empty and error states |

### Vector screens (`screens/`)

All ten screens are **true vector SVGs** at 1440 × 900: panels, borders, table text, chips, plots and icons are editable shapes and text, with no screenshots. The one exception is the 3D trajectory figure in `E5-3d-dark.svg`, which is a canvas and is embedded as an image. CSS gradients, hatching and blur are flattened.

| Screen | File |
|---|---|
| Mixed model (recorded run) | `screens/E4-mixed-model-light.svg` |
| 3D trajectories | `screens/E5-3d-dark.svg` |
| Specification changed | `screens/E6-stale-light.svg` |
| Command palette | `screens/E7-palette-dark.svg` |
| Descriptives | `screens/E8-descriptives-light.svg` |
| Paired T-Test | `screens/E9-ttest-dark.svg` |
| Repeated-measures ANOVA | `screens/E10-anova-light.svg` |
| Linear regression + Variables view | `screens/E11-regression-light.svg` |
| Athlete change | `screens/E12-athlete-change-dark.svg` |
| Reliability (recorded run) | `screens/E13-reliability-light.svg` |

Re-export one screen from the running prototype (port 8605). `export-svg.js` turns the live page into SVG when the URL hash contains `svgexport`. A 1464 × 992 headless window gives a 1440 × 900 viewport:

```bash
msedge --headless=new --window-size=1464,992 --virtual-time-budget=7000 --dump-dom "http://localhost:8605/e-workbench/#lmm,svgexport" > dump.html
```

The SVG is the contents of `<textarea id="svgout">` (HTML-unescaped). Screen hashes: `lmm`, `dark,3d`, `stale`, `dark,palette`, `desc`, `dark,ttest`, `anova`, `reg,vars`, `dark,change`, `icc`.

Rebuild the sheets after a token or layout change: `python build_svgs.py` in this folder. The tokens in `build_svgs.py` are the single source and must match `res620-prototypes/common.css` (light) and `e-workbench/index.html` (dark). Sheets 04 and 05 embed the vector screens from `screens/` by relative path.

## Rules that cannot change

1. **Three kinds of claim, never blended:** observed (graphite, solid), modeled (cobalt, always with its interval), hypothetical (ochre, hatched, locked until RES-590).
2. **Provenance and method status are separate axes** from the kind of claim. Every result block shows its claim chip, provenance chip, a limits note and a provenance footer (method status · run · digest).
3. **Only qualified methods can be promoted to evidence.** Descriptive and not-qualified analyses say so on the block and in the syntax comment.
4. **Diagnostics keep their exact RES-619 names**, e.g. "marginal residual / conditional SD", labelled EXPLORATORY.
5. **Missing data is always visible** (red dash, dashed ring). It is never blank and never silently imputed.
6. **Every GUI state has a Python syntax equivalent**, shown in the syntax bar.

## Qt implementation map

| Design element | PySide6 / existing stack |
|---|---|
| Shell, three panes, splitters | `QMainWindow` → central `QSplitter` (Data · Options · Results), state in `QSettings`; panes are `QFrame`s on the desk colour |
| Ribbon | `QToolBar` with `QToolButton` (`ToolButtonTextUnderIcon`), exclusive `QActionGroup` |
| Tokens and themes | `QPalette` per theme + one generated stylesheet in `desktop/theme.py`; no per-widget `setStyleSheet` |
| By athlete / Variables / Rows | `QTableView` over a pivot proxy (`QSortFilterProxyModel` subclass); `QStyledItemDelegate` for sparklines and missing marks; header click selects the variable |
| Variable assignment | `QListView` + model with `mimeData`/`canDropMimeData` type rules; role boxes as small list views; rejection = status message + shake animation (`QPropertyAnimation`) |
| Option sections | Collapsible `QGroupBox`es (or `QToolBox`) bound to the analysis spec |
| Stale state and run | Spec hash vs run spec; `QGraphicsOpacityEffect` on dependent blocks; existing `TaskRunner`/worker |
| Results document | Vertical stack of result widgets in a `QScrollArea`; publication tables as `QTableView` with a custom header painter or `QTextBrowser` HTML tables; Matplotlib canvases for exportable figures |
| Interactive figures | pyqtgraph `PlotWidget`; **3D trajectories** with `pyqtgraph.opengl` (`GLViewWidget`, `GLScatterPlotItem`, `GLMeshItem`) |
| Command palette | Frameless `QDialog` + `QLineEdit` + filtered `QListView`, `QShortcut(Ctrl+K)` |
| Syntax bar | Read-only `QPlainTextEdit` (Cascadia Mono) + Copy button |
| Inspector raw detail | Behind View ▸ Advanced only (RES-613 finding) |

## Implementation plan (each step = one validated `RES-620` commit)

1. **Tokens and theme.** Generate the light and dark palette and stylesheet from these tokens into `desktop/theme.py`. Remove scattered inline styles. Add a contrast check test.
2. **Shell.** Ribbon, three-pane splitter, status bar, saved layout, Ctrl 1/2/3 focus, F6 cycling, accessible names.
3. **Data pane.** Pivot proxy with By athlete / Variables / Rows views, sparkline delegate and missing marks, for Mendeley and MoveSmart.
4. **Assignment and options.** A generic analysis spec model, role boxes with type rules, collapsible sections, live syntax generation.
5. **Results document.** Result block widget (chips, note, provenance footer), publication tables, stale state, Run via the existing worker, Promote gated on method status.
6. **Analyses.** Wire Mixed Models and Reliability to the qualified engine first. Descriptives, Frequencies and Athlete change come next as descriptive. T-Test, RM ANOVA and Regression only as clearly labelled not-qualified tools, or deferred to a methodology issue. No methodology changes in RES-620.
7. **Figures.** Port the plot styles to Matplotlib (export) and pyqtgraph (interactive), then add the 3D trajectories view.
8. **Command palette, keyboard, DPI.** Palette and shortcuts, then 1366 × 768 at 100 % and 150 %. Multi-monitor checks are marked untested where no hardware is available.

## Open items to verify in Qt (not decided by this spec)

- The 150 % layout drawer behaviour (sheet 03) needs an on-screen check.
- Whether T-Test, ANOVA and Regression ship in the first release or wait for qualification. This is a product and methodology decision, not a design one.
- Profile-likelihood intervals and random-intercept normality remain RES-619 review items. The design only reserves where they appear.
