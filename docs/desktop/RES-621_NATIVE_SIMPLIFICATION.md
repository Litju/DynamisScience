# RES-621 focused native simplification

Development continuation on 2026-11-17, starting at `1f6521c` in the existing
checkout. The longitudinal workflow is reused. No estimator, scientific method
contract, persistence schema, report renderer or operational dataset is changed.

## Native baseline before editing

`tests/test_research_compact.py` opened the actual MainWindow, athlete protocol,
series roster and admitted Parquet preview through the existing task selectors.
Two synthetic experiments and the existing 12-participant admission fixture were
used for geometry inspection; this is not a new usability study or a replacement
for the existing 20-athlete integrated journey.

Qt's **offscreen** platform, explicitly loaded Segoe UI 10, requested and actual
window sizes 911×480, 1024×640 and 1366×720. Baseline screenshots and JSON receipt:
`D:/SWE_HOME/codex_home/artifacts/res621-compact-before/`. Screenshots were inspected.
An initial capture accidentally left the Squad perspective active and was rejected;
the retained baseline uses supported scope/stage navigation to the actual surfaces.

| Surface | Reproduced baseline | Change and observed benefit |
| --- | --- | --- |
| Series roster | 1,335 px columns in 823 / 936 / 1,278 px viewports; horizontal scroll required even at 1366 | Six wrapping columns fit the viewport; zero horizontal-scroll maximum at all three geometries. Selection binds to the member stored with the item, so header sorting cannot change athlete identity. |
| Experiment comparison | Horizontal participant panels each required at least 330 px; more participants consumed width | Vertically stacked participant panels retain separate axes and complete timelines. Full captured design, eligibility and result/provenance are accessible through Inspect selected experiment details. |
| Data preview | Session/trial/instrument/protocol IDs and sampling preceded the week and measurements | Athlete and week lead, followed by body mass (kg), jump height (cm), force (N). Source QC and synthetic validity context precede the preview. Technical columns are one disclosure away; selected-row details retain every raw field and revision/snapshot identity. Full-value tooltips preserve precision. |
| Protocol | Save was outside the visible viewport at all three sizes; vertical scroll range 616 / 456 / 359 px | Pending second change. |
| Toolbar | Nine actions occupied the workspace toolbar; protocol/result context overflowed at 911 | Pending second change. |

## First independently validated change

Scoped command: `services/science/.venv/Scripts/python.exe
services/science/scripts/scoped_tests.py tests/test_research_compact.py
tests/test_native_experiment_series.py tests/test_native_experiments.py -x -ra`.
The native checks exercise sorting, selection and frozen capture identities,
full-row provenance, technical disclosure, canonical units, full-value tooltips,
existing two-athlete protocol/visit workflow, frozen history and stale callbacks.

No physical Windows display, hardware DPI or screen-reader verification is claimed.
The owner's modified manifest remains excluded; the private dataset is not opened.
Test writes are isolated by the existing bounded runner, with guarded scratch cleanup.

First change result: **7 passed in 22.87 s**, sampled scratch peak **4,539,752 bytes**, scratch removed. Evidence: D:/SWE_HOME/codex_home/artifacts/res621-compact-tables/.
