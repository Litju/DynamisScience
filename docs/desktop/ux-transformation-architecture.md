# DynamisScience interaction architecture

The workspace follows the order in which a scientific question becomes evidence. Open or resume in **Library**. Inspect people and observations in **Investigate**. Define or conduct a study in **Design**. Use **Analyze** for scientific methods and the exploratory workbench. Return to immutable records and existing export in **Evidence**. Run daily practitioner tasks in **Operations**. Each destination has a persistent native entry and takes its context from the open study or the explicitly selected operations record.

| Decision | Researcher experience | State boundary |
| --- | --- | --- |
| Workspace selection | Open, create or resume a study. See what can be done before adding measurements. | Opening, closing and switching views use the existing workspace identity. |
| Participant and evidence | Choose a subject and assessment pair once in investigation. Open observations with date, unit, quality and source. | A historic view displays its own revision. Changing destinations leaves that view available. |
| Study and analysis | Put authoring, actual conduct, cohort and method entry along a task sequence. Give the exploratory workbench its own destination. | Eligibility, revision binding, stale-run behavior and promotion still come from the scientific services. |
| Evidence and export | See recorded result, interpretation and provenance before exporting or comparing frozen versions. | Historic artifacts and report bytes remain immutable. |
| Operations | Give Today, Athlete 360, Plan, Monitor, Test, Match & Pose, Research and Reports a clear route. | Operations has its own scope. Open linked research explicitly. |
| Spatial | Start in 2D. Open a labeled spatial view on demand. Maintain shared selection, explicit depth and camera controls. | Use the existing measured and modeled values and method-defined layer availability. |

Use a shared Qt palette for graphite and light themes with one prominent action per task, a consistent focus outline, semantic status colors, readable labels and native form behavior. Treat resize as a layout event and keep dense specialist tools available through bounded scroll or inspectors. Keep animation off when reduced motion is requested. QPainter and OpenGL remain suitable for the existing spatial views. Replacing the native stack would add migration and proof burden without solving a demonstrated requirement.

## Implementation sequence

1. RES-755 records the capability inventory, branch and feedback baseline, and this task architecture.
2. RES-756 delivers the shared shell and reusable visual and interaction primitives. Verify cold launch, direct navigation, accessible naming, and transitions across scopes with the same source and identifiers.
3. RES-757 covers source/QC, investigation, design, experimental conduct and comparison. Verify ambiguous import/refusal, selection preservation and live/frozen round trips.
4. RES-758 covers specialist workbench, results and reporting. Verify variable roles, exact eligible run, stale rerun, provenance and frozen export.
5. RES-759 covers operations and optional spatial interaction. Verify operations pages and linked research, 2D/3D selection continuity, camera controls and OpenGL fallback.
6. RES-760 qualifies the combined experience, with conventional keyboard workflows, compact window, native 100/125/150% checks, reduced motion, matched elapsed times and independent owner acceptance.

## Matched acceptance scenarios

Use an isolated source-run Windows instance and record its Git source, platform, actual window dimensions and data identity. Keep the operational private database and owner manifest outside the run. Retain compact synthetic-only before/after visuals and a receipt. Mark each step verified, failed, or awaiting evidence. Timing and detours recorded by an operator belong to the operator run. The unassisted owner result has its own record.

- Cold launch → open workspace → athlete/cohort → find comparison and eligibility → inspect real source links → frozen history → back to live → select unequal assessment support. Match the separate A01/A20 acceptance fixture where available.
- Import a changed measurement or training source with a known conflict → review suggested mapping, units and QC → approve or quarantine → reopen the correct new revision, with the original stable.
- Create or open a study → configure cohort and protocol → record conduct → review method eligibility → run → compare experiments → inspect provenance → export → reopen historic report and compare bytes.
- Operate across all Performance pages → open athlete and inspect measures/pose → return to the same study → open 2D/3D trajectories → inspect the same athlete using keyboard and mouse.
- Repeat representative paths with a compact physical window and at 100/125/150% native display settings. Check readable copy, pointer-free focus order, system feedback, reduced motion, chart interactivity and render latency.
