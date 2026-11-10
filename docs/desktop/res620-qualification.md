# RES-620 Gate 5: installed-application qualification

Source: commits e20bf36 .. 5c55066 on main (installer built from 5c55066; closing round g6 follows). `data/synthetic/generator_manifest.json` stays modified and uncommitted.
Method: the real entry point (`python -m dynamis_science.desktop`, `QT_QPA_PLATFORM=windows`) on isolated copies of the private root, driven programmatically; screen-by-screen comparison in [res620-comparison.md](res620-comparison.md); screenshots in `res620-evidence/`.

## Defects fixed

| # | Defect | Fix | Commit |
|---|---|---|---|
| 1 | Descriptives options cited METH-REAL-DESC v1.1.0 / QUAL-REAL-DESCRIPTIVE while the result said "Not a recorded run" | Descriptives, Frequencies and Athlete change run live in pandas: `method_status` has no method id, Options says "live workbench descriptive, no method record, cannot be promoted" | e20bf36 |
| 2 | By athlete delta "-0.0" | Rounded zero prints as 0.0 | e20bf36 |
| 3 | By athlete Value defaulted to body_mass_kg | Follows the spec outcome, including later changes | e20bf36 |
| 4 | Syntax bar cut the third line | Sizes to wrapped lines (6 max, 4 below 800 px, 3 below 600 px), scrolls with a scrollbar beyond that; Athlete change syntax prints plain levels | e20bf36, 8ead8d7 |
| 5 | 3D view tiny | Camera distance 21 -> 14 | 617bf3d |
| 6 | Performance OS "Athletes to review" headers clipped | 8 px headers, wider columns | 617bf3d |
| extra | E7 palette lacked "Assign <variable> as <role>"; Data pane tables unnamed; Variables headers clipped | added / named / widened | a792e0d, 8ead8d7, e20bf36 |

## Qualified workflows through the GUI (isolated copy)

- MixedLM (STUDY-REAL-001, cmj_height_cm ~ occasion, subject_id): ML, random intercept + occasion slope, 82 observations, 21 athletes, log-likelihood -208.31, intercept 38.650 (SE 1.753), slope 0.998 (SE 0.192, CI 0.622 to 1.375), change 1 to 4 2.995 cm (CI 1.866 to 4.124), digest 519fe130, identical to recorded RUN-REAL-0005 and to the R lme4 comparison in `real_qualification.json`.
- Reliability (STUDY-REAL-002, fz_peak_n, Walking): ICC(3,1) 0.8887, CI 0.7452 to 0.9693, ICC(2,1) 0.895, ICC(1,1) 0.895, TE 75.78 N, MDC95 210.05 N, analysed 9 athletes x 5 trials = 45, excluded MS-06 and 37 trials, catalogue 10 participants / 82 eligible trials, digest e0eedb0e, identical to recorded RUN-REAL-0004.
- Promote + Add to report on a current run: EVID-REAL-0001 / FIG-REAL-0001 cited in REPORT-REAL-001 (section "Intervention result"); reliability promotion also succeeded. Raw values: `res620-evidence/workflows-observed.json`.
- Superseded runs: RUN-REAL-0001 (METH-REAL-TREND 1.0.0) and RUN-REAL-0002 (METH-REAL-RELIABILITY 1.0.0) show the "Historical result, superseded method version" bar, Promote and Add to report are disabled, and `promote()` / `add_to_report()` return nothing with the reason in the toast. RUN-REAL-0005 (1.1.0) promotes.

## State

Spec change after a run: stale (banner, dimmed results, promote disabled); change back: current; rerun: new run, current. Opening another study clears results, syntax, promote and run state. Switching Mixed Models to Reliability or Descriptives keeps the previous result on screen but flagged "Specification changed" and non-promotable (one results document, by design); no outdated result is promotable.

## Closing round (g6): items fixed after the first Gate 5 pass

| # | Item | Fix | Commit |
|---|---|---|---|
| 1 | Descriptives had no statistic/plot options (E8) | Statistics (N and missing, mean and SD, median and IQR, min and max, 95 % CI of the mean as a t interval of the observed mean) and Plots (box plot with points, histogram) are checkboxes bound to `spec.options`, shown in the syntax bar, the result table columns and the figures; "at least one statistic" is validated. Descriptive only | 5593fb4 (+ 0c47d19 EOL restore) |
| 2 | Variables view lacked Role and Distribution (E11) | Role = current spec role label per variable, Distribution = mini-histogram delegate from at most 2000 bounded rows (levels or distinct count as text for non-numeric) | 6326e6d |
| 3 | Tab order after Assign visited Results before the role boxes | variables -> assign -> role boxes -> option section toggles and fields (03-layout focus model); verified by UIA tab walk | 3baf2d1 |
| 4 | "Not available in the qualified engine" truncated | Wraps to three lines, tooltip carries the text | 3baf2d1 |
| 5 | Run id only in export metadata | PNG, PDF and SVG print "Run <id> · <method> <version> · method status <state> · result digest <8>" on the figure; checked in PNG (viewed), SVG text and PDF text streams, and in the installed build | 5c55066 |
| 7 | `build_windows.ps1` stopped silently before Inno Setup | Root cause: under `$ErrorActionPreference = "Stop"`, Windows PowerShell 5.1 turns every stderr line of a native command (uv, PyInstaller warnings such as the missing MSVCR90/100 DLLs) into a terminating NativeCommandError once the caller merges streams (2>&1, hidden launcher). Reproduced with a 6-line script. Native calls now go through `Invoke-Native` (stderr kept as text, exit code decides, tail printed and throw on failure); `$repoRoot` (undefined) is defined; the installer file is checked. The rebuilt script produced the installer end to end when launched with stderr merged | c8bf3a8 |

## Owner review round (1141fbf)

- **Zoomed-in look on the owner's 1366x768 screen (100 % Windows scaling).** The 1440x900 layout did not fit the 1366x728 work area, so chrome and padding crowded the panes. Before `QApplication` starts, `_apply_fit_scale` reads the primary work area and sets `QT_SCALE_FACTOR = max(0.85, min(1, w/1440, h/860))`; it never enlarges and a user-set `QT_SCALE_FACTOR` wins. On 1366x768 the UI renders at 0.85 with a 1607x824 logical window, the same proportions as the design (panes 619 / 320 / 636). Evidence: `res620-evidence/owner-fit-1366x768-reliability.png` (isolated copy of the private root, Reliability run e0eedb0e).
- **Options header stuck on "Mixed Models".** Root cause: the header text was set only from `QAction.triggered`, so checking an analysis through accessibility toggles, the palette or restore skipped it. The header, saved analysis and `analysis_selected` now follow `toggled`. Regression test: `test_options_title_follows_every_way_the_analysis_changes`.

## Keyboard and accessibility

Ctrl+1/2/3 and F6 move focus Data / Options / Results with a visible focus frame on the pane; Ctrl+K opens the palette; Ctrl+Enter runs (stale -> current); variables can be assigned from the palette ("Assign x as outcome") and the Assign button. Widget walk: 48 visible controls, one lacked a name (the Variables/Rows table) and is now named. Tab order is fixed (item 3): Assign -> Outcome / Subject / Occasion / Covariates / Factors role boxes -> Model section toggle -> option fields -> Results document.

## Exports

PNG, PDF and SVG exported through the GUI export path (`_export_results`), also from the installed build via the Export dialog (`export-inst`, 3 formats x trajectory/residuals). The figure face now carries the run id, method id and version, method status and result digest (item 5); embedded metadata (PDF info, SVG metadata) is unchanged. PDFs embed TrueType fonts with text-show operators; SVGs keep text elements (`svg.fonttype none`). Evidence: `res620-evidence/installed2-export-trajectory.png`, `installed2-export-residuals.png`.

## Installer (final, source-matched)

- File: `services/science/build/res604-20261110-185620-eb28876c/dist/installer/DynamisScience-Setup-x64.exe`, 142,743,924 bytes (not committed)
- SHA-256: 4512F7187D5F1E8C35D25565A4A9747636F36C366F5B14C8E70974D99547B192
- Source commit: 1141fbf (working tree: only `data/synthetic/generator_manifest.json` modified); commits after it are documentation only
- Built by `scripts/build_windows.ps1`, exit 0. Installed silently to a scratch folder, launched maximized on the 1366x768 display against an isolated copy of the private root: UI at fit scale 0.85, ribbon, panes and library in proportion; switching to Reliability through the UI Automation toggle (the path that left the header stale) now shows "Reliability". Closed and uninstalled (exe gone). Evidence: `res620-evidence/installed3-fit-reliability.png`.
- Scientific code is unchanged since the previous installed build (5c55066, SHA-256 D2B6213E...), whose installed results follow; the numbers were not re-run in the final build.

- Installed with `/VERYSILENT /DIR=<scratch>\inst` (no previous installation, no uninstall key), launched with `--data-root` pointing to an isolated copy of the private root and driven through UI Automation; uninstalled afterwards (exe gone, uninstall key gone).
- Installed app results: workbench opens with the new Role / Distribution columns and wrapped role placeholders; MixedLM (ML, 82 obs, 21 athletes, intercept 38.650) digest **519fe130** (RUN-REAL-0006 and 0007, identical); Reliability (STUDY-REAL-002, fz_peak_n, Walking) ICC(3,1) **0.8887**, CI **0.7452 to 0.9693**, digest **e0eedb0e** (RUN-REAL-0008); "Add to report" through the GUI promoted and cited EVID-REAL-0001/0002 + FIG-REAL-0001/0002 (STUDY-REAL-001) and EVID-REAL-0003 + FIG-REAL-0003 (STUDY-REAL-002); PNG/PDF/SVG exports with the footer (PNG viewed); the 3D view rendered (OpenGL bundled). Screenshots: `res620-evidence/installed2-*.png`.
- One driver slip, not an app defect: the first Export attempt typed a path with doubled backslashes into the file dialog and Windows rejected it ("The file name is not valid"); with a correct path all three formats exported.

## Test suite

`QT_QPA_PLATFORM=offscreen uv run pytest -q`: full runs on the final code, 171 passed (169 earlier plus the two owner-round tests), 0 failed, 0 skipped each (junit counts).

## Open limitations

- **Flaky journey test not root-caused.** `tests/test_desktop.py::test_native_research_journey_executes_promotes_freezes_and_exports` failed once in an earlier full run (report freeze validation) and passes alone. Tried: 6 isolated repeats (pass), 3 full-suite runs with default order (pass), a loaded run with 4 busy processes (pass), 12 and 10 busy processes on 4 cores (failed: pytest printed `F` and then hung without a traceback, so the failure message was not captured). Readings of the test and `TaskRunner`/report code found no shared module state (the store resolves the root per call, settings live in the per-root `desktop/workbench.ini`); the signature points to timing under CPU contention (`qtbot.waitUntil` default 5 s windows around worker-thread report operations, and `QThreadPool` tasks still running when assertions fail). Not fixed; timeboxed per coordination. Next step: give those waits explicit generous timeouts, drain the runner in a fixture, and capture the failing message with `--tb=short -o faulthandler_timeout`.
- Descriptives table with all five statistic groups on is 9 columns wide and scrolls horizontally in the 551 px Results pane; the checkbox indicator is a filled square without a check mark (existing theme). Distribution uses at most the first 2000 rows. t-test level pickers remain text boxes.
- 3D needs scrolling in windows under about 600 px; "By athlete" segmented label clips at 150 % compact.
- Only a 1366x768 display was available: 1440x900 and 150 % are logical emulations (QT_SCALE_FACTOR), multi-monitor untested.
