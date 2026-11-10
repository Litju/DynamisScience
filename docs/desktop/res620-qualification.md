# RES-620 Gate 5: installed-application qualification

Source: commits e20bf36 .. 8ead8d7 on main (HEAD 8ead8d7 at installer build). `data/synthetic/generator_manifest.json` stays modified and uncommitted.
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

## Keyboard and accessibility

Ctrl+1/2/3 and F6 move focus Data / Options / Results with a visible focus frame on the pane; Ctrl+K opens the palette; Ctrl+Enter runs (stale -> current); variables can be assigned from the palette ("Assign x as outcome") and the Assign button. Widget walk: 48 visible controls, one lacked a name (the Variables/Rows table) and is now named. Remaining: Tab order after the Assign button visits the Results document before the role boxes.

## Exports

PNG, PDF and SVG exported through the GUI export path (`_export_results`). PNGs viewed (trajectory, residuals, reliability). PDFs embed TrueType fonts with text-show operators; SVGs keep text elements (`svg.fonttype none`). The run id (RUN-REAL-0006 / RUN-REAL-0007) and digest are in the embedded provenance metadata (PDF info, SVG metadata), not printed on the figure.

## Installer

- File: `services/science/build/res604-20261110-124745-22c9a057/dist/installer/DynamisScience-Setup-x64.exe`, 142,735,346 bytes
- SHA-256: 1A1DB2BB75C4FB9A9E119F80B12E3F03209F686D66D5A61736416132F55ED7F1
- Source commit: 8ead8d713faeee77c85e5e0ee89ae7bc1504846f (working tree: only the generator manifest modified)
- `build_windows.ps1` completed PyInstaller but stopped silently before Inno Setup when launched hidden; ISCC.exe was then run with the script's own arguments.
- Installed with `/VERYSILENT /DIR=<scratch>` (no previous installation existed), launched against an isolated root copy, then uninstalled. The workbench opened; via UI Automation and keyboard only (palette assignment, Ctrl+Enter) a MixedLM run gave ML, 82 observations, 21 athletes, 38.650, digest 519fe130 (RUN-REAL-0006); the 3D trajectory view rendered with PyOpenGL bundled (`installed-mixedlm-run.png`, `installed-3d-view.png`; screen is 1366x768 at 100 %).
- Not re-run on the installed build: reliability, promotion, exports (covered on the source build above).

## Limitations

- Descriptives have no statistic/plot options (E8 prototype has them); Variables view has no Role/Distribution columns; t-test level pickers are text boxes.
- Tab order defect above; 3D needs scrolling in windows under about 600 px; "By athlete" segmented label clips at 150 % compact; Options "Not available in the qualified engine" is truncated.
- Run id is not printed on exported figure faces.
- Only a 1366x768 display was available: 1440x900 and 150 % are logical emulations (QT_SCALE_FACTOR), multi-monitor untested.
- Full suite (`QT_QPA_PLATFORM=offscreen`): run 1 had 161 passed and 1 failed, `test_native_research_journey_executes_promotes_freezes_and_exports` (report freeze validation); that test passes alone and the whole suite then passed 162 of 162. Treat it as an order-dependent flake, not diagnosed.
