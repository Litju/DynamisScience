# RES-621 native research UX handoff

## Disposition

The owner rejected the current experience and requested a handoff of the work as it stood on November 20, 2026. Usability acceptance remains open. The native synthetic demo was left running on live A01 for inspection.

## Implemented

- **Investigate** opens with one selected athlete or cohort, assessment dates, a live or frozen revision, the observed finding, and a clickable training and testing timeline. The finding states the limits of the descriptive comparison.
- **Study** groups people, source quality, study setup, experiment comparisons, archive, and formal analysis. Its Renaissance-inspired 3D map supports drag rotation, arrow keys, and point selection. The same destinations are reachable by keyboard through native buttons.
- Selecting an athlete in People opens Investigate directly. A selected planned phase or recorded visit opens its corresponding editor. The live timeline returns to the selected evidence and reuses its comparison when the underlying data remain valid.
- Sources & quality shows attached measurement, training, and wellness sources, QC, and missingness. Measurement rows, raw study metadata, and detailed provenance are available on demand. The CSV flow uses the existing reconciliation, rights, QC, and source-versioning paths.
- Specialist method, protocol, report, and operations forms remain comparatively dense. The consolidation of navigation did not resolve the owner's usability concerns.

## Validation

| Check | Outcome |
| --- | --- |
| Final 20-athlete study and training context scope using Qt's Windows platform | 18 passed in 36.69 s. Covered chart evidence, the visit editor after a data revision, A20 trial-count refusal, frozen history, import approval and quarantine. Scratch removed. |
| Navigation milestone | 7 passed in 88.61 s. Covered the compact layout, native navigation, and the 12-week research journey. Scratch removed. |
| Workbench and scientific regression scope on the navigation milestone | 41 passed in 269.73 s. Covered existing methods, experimental conduct, randomized-onset eligibility, measurement trust, and workbench layout. Scratch removed. |
| Additional combined scope during source-page development | Stopped by the 300 s bound. Scratch removed. This run does not count as passed. |

The live Windows walk-through used the existing disposable synthetic study in a 1366 × 720 work area. It opened Sources & quality through a projected 3D control, opened a recorded visit from timeline evidence, and restored the cached **+3.75 cm** live comparison after viewing the **+2.75 cm** frozen revision. A synthetic observed change carries no qualified meaningful-change or causal claim. The Windows walk-through used scripted Qt input. The owner remains the usability acceptance authority.

Screenshots and the Windows receipt are local under `D:/SWE_HOME/codex_home/artifacts/res621-renaissance/`. They include Investigate, Study, Sources & quality, timeline evidence, the selected visit, and the frozen revision.

## Preservation

The scientific estimators and existing frozen artifacts were preserved. Tests used disposable synthetic data. The owner-modified `data/synthetic/generator_manifest.json` is excluded from this handoff, and `D:/datasets/DynamisScience` was outside the test and capture paths.
