# RES-620 Gate 5: reference vs real application (side by side)

Reference = `docs/desktop/res620-design/screens/E*.svg` rendered with msedge at 1440x900 (`ref-E*.png`).
Actual = real entry point `python -m dynamis_science.desktop` (QT_QPA_PLATFORM=windows), Mendeley STUDY-REAL-001 / MoveSmart STUDY-REAL-002 on an isolated copy of the private root, driven by `drive.py`.
The prototype uses illustrative data and a different dataset (athlete_id, Pre/Post columns); only structure, state and chrome are compared.

| Screen | Verdict | Remaining deviations |
|---|---|---|
| E4 mixed model (light) | Match | Real data columns/rows. Results show the qualified ML engine (random intercept + occasion slope, 82 obs, 21 athletes), more tables than the prototype (variance components, contrasts). Covariate/Factor role boxes show truncated "Not available in th..." at 320 px. |
| E5 3D (dark) | Match after fix | Camera distance 21 -> 14 so the scene fills the GL view. Prototype shows axis titles inside the box and a lighter grid; ours uses pyqtgraph text items. GL view is 467 px wide, not full results width, by design of the card padding. |
| E6 stale (light) | Match | Same banner, dimmed results, disabled Add to report, Run button. Run button label clips "Ctrl" at 100 %. |
| E7 palette (dark) | Match after fix | Added "Assign <variable> as <role>" commands (were missing). Palette shows all matching, not the prototype's three. |
| E8 descriptives (light) | Partial | Provenance now honest ("live workbench descriptive, no method record"). Prototype has Statistics / Plots checkbox groups (min/max, 95 % CI, histogram); ours has fixed N, missing, mean, SD, median, IQR and one box plot, "no options" text. Split by occasion shows level numbers (1..4), the prototype shows names. |
| E9 t-test (dark) | Deliberate difference | Frozen RES-619 matrix: NOT QUALIFIED, "Unavailable in the qualified engine", Add to report disabled, no run, no digest. The prototype's illustrative t-test result is intentionally not implemented. Level 1/2 are free-text boxes (prototype: dropdown). |
| E10 ANOVA | Deliberate difference | Same as E9. |
| E11 regression + Variables | Deliberate difference + partial | Unavailable/not promotable as E9. Variables view has Type/Unit/N/Missing/Missing %/Quality columns; prototype has Role and Distribution mini-histograms (not implemented). "Quality" column clipped at 536 px (horizontal scroll). |
| E12 athlete change (dark) | Match | No-threshold status, per-athlete bar chart and table, By athlete Value follows the outcome. Syntax no longer prints np.int64(4). Prototype options (Compare From/To dropdowns, SWC threshold field, Sort) are spin boxes and fixed sort. |
| E13 reliability | Match, better | ICC(3,1) 0.889, CI 0.745-0.969, TE 75.78 N, MDC95 210.05 N identical. Ours adds the catalogue (10 participants / 82 trials) vs analysed (9 x 5 = 45, MS-06 excluded, 37 trials excluded) cohort table the prototype lacks. Data pane is Variables, not the By participant grid (no occasion column in signal_trials). |
| Performance OS Today | Fixed | Attention table headers clipped at 8 px cells with 13 px bold headers; now 8 px headers, wider columns. |

## Sizes and DPI (logical window = physical / scale)

| Physical | Scale | Logical | Layout | Result |
|---|---|---|---|---|
| 1440x900 | 100 % | 1440x900 | 3 panes 537/320/551 | readable, matches E screens |
| 1366x768 | 100 % | 1366x768 | 3 panes 510/300/524 | readable; syntax bar is 4-5 lines |
| 1440x900 | 150 % | 960x600 | compact (icon ribbon, Options drawer) | readable |
| 1366x768 | 150 % | 911x512 | compact | readable; Results viewport ~200 px high, so 3D view needs scrolling; "By athlete" segmented button clips its first letter |
