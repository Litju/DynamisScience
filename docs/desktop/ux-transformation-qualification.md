# Native UX transformation qualification

The implementation is a stack of draft changes above the reconciliation branch at `2c911f5`. The existing Python services, scientific algorithms, storage schemas, source bytes and immutable research artifacts remain under their existing authority. This work changes presentation and interaction. The owner still determines whether the experience is acceptable in live use.

## What was exercised

| Journey | Observed result | Remaining acceptance work |
| --- | --- | --- |
| Library and navigation | Opened the disposable study through the native chooser. Traversed Investigate, Design, Analyze, Evidence and Operations. Tab reached Design from Investigate. Operations round trip retained athlete and revision. | An unassisted first-time researcher needs to establish discoverability with representative project and cohort choices. |
| Data management and admission | Data Workspace and import opened as native dialogs. Targeted tests exercised dataset search, immutable batch binding, QC, unresolved mapping, approved reconciliation and quarantine. | Long-source names and unassisted correction workflows across all vendor formats need observation. |
| Investigation and protocol | The baseline investigation repeated phase labels until they overlapped. The new chart shows spaced phase changes and point evidence on demand. The separate 20-athlete suite exercised dated A01/A20 measurements, comparison eligibility, source inspection, context import and return from frozen history. Squad and Events open the selected athlete's investigation. The live investigation links to the athlete record and its branches. | Reproduce the owner task unassisted with recorded detours and elapsed time. Specialty protocol and analysis forms still need user review. |
| Analysis and evidence | The workbench exposes setup and Run, with syntax available on demand. Verified study and individual runs, evidence promotion, versioned report writing, frozen reports, and export. Frozen follow-up output matched the original report bytes. | Additional accessibility observation is needed for deeply nested diagnostic and versioned lifecycle dialogs. |
| Operations and spatial interaction | All eight Operations destinations opened from the navigation rail. Focused Windows regression covered reports, monitoring, athlete details, signals and measured 2D/3D selection with an identical readout on return. Missing OpenGL has an explicit fallback. | Assess camera and pointer discoverability with a researcher. Compact scientific plots and tables may need scrolling. |
| Preferences, keyboard and resizing | Verified dark and light themes, the native preferences dialog, persisted reduced motion, compact layout and the 150% work-area boundary. The first 150% run revealed overflow from the Operations rail. The corrected window retained a 666 px physical client height. Compact Operations switches to a keyboard-accessible page picker, keeping the main actions visible. | System display scaling, screen readers, all external monitor geometries and the installed build require separate checks. |

## Reproduce the source-run walkthrough

Run from `D:\projects\DynamisScience\services\science` with the repository environment:

```powershell
& ./.venv/Scripts/python.exe scripts/qa_run.py run --issue RES-760 --max-scratch-mib 450 --min-free-mib 1024 --timeout-seconds 120 -- ./.venv/Scripts/python.exe scripts/native_ux_walkthrough.py --scale 1.5
```

The walkthrough creates a disposable 20-athlete study and fresh Qt session. Scale is per process, and the receipt records the actual Qt device-pixel ratio and work area. Actions use Qt input on visible Windows widgets. Each capture is source-run and synthetic. Script timings include event settling and capture. A route sweep can show correctness and visible defects. It supplies no independent speed, comprehension, or usability claim.

All 22 steps completed at each ratio on application source `03151c8`.

| Qt device-pixel ratio | Logical work area | Physical client during full-size route sweep | Logical compact client |
| --- | --- | --- | --- |
| 1.00 | 1366 × 720 | 1350 × 684 | 1200 × 604 |
| 1.25 | 1093 × 576 | 1346 × 675 | 927 × 460 |
| 1.50 | 911 × 480 | 1343 × 666 | 745 × 364 |

1. Opened the cold Library and selected a study in the native chooser.
2. Loaded the investigation, opened the athlete record, and returned to the active study Library.
3. Opened study design, frozen evidence, the analysis workbench, Data Workspace and measurement import.
4. Traversed Today, Athlete 360, Plan, Monitor, Test, Match & Pose, Research and Reports in Operations.
5. Returned to the same athlete and data revision in Investigate.
6. Opened preferences, selected light appearance and reduced motion, verified Tab focus, and resized to a compact window.

Representative evidence is retained in `D:\SWE_HOME\codex_home\artifacts\dynamisscience-ux-2026-11-22`. It includes the original Windows investigation baseline, the new research workspace and representative Operations views. Private Mendeley and MoveSmart sources were exercised in checksum-verified isolated regression copies. Their source trees and the owner's dirty generator manifest were protected and verified unchanged.

## Regression evidence

- RES-757 passed 40 Windows-platform tests for investigation, context, source reconciliation and admission. RES-759 passed six Windows-platform Operations and spatial tests. RES-761 passed 49 Windows-platform tests for data, import, Squad, experiments, comparison and research context. The suites overlap.
- RES-758 exercised both report workflows and admitted data on the Windows backend. The native run recorded 48 passes and one failure because the exact 1440 px offscreen design fixture was run against a smaller physical desktop. The separate 27-test offscreen theme and pane suite passed.
- The full 440-case attempt on `17ef41b` reached 65% and exceeded its 850-second child bound. That attempt is incomplete. Its three observed failures covered Operations width, the former Squad-to-athlete route, and the former event-to-athlete route. Corrected flows passed together on `03151c8` with no scientific engine change.
- A later batch and its initial continuation stalled in an unattended workflow test. The test now waits for pending source review before closing and records an unexpected importer route directly. Both workflow cases passed on the corrected harness.
- The 152 remaining collected cases passed on `7d3b6c8` in 374.45 seconds with no failures or skips. Coverage included scientific workbench and admitted data, persistent lifecycle and frozen reports, training context, storage isolation, and result export. This is a source-specific continuation and targeted recovery, with the earlier full-suite attempt still recorded separately.

## Review stack

| Issue | Scope | Draft |
| --- | --- | --- |
| RES-755 | Inventory and task architecture | [#6](https://github.com/Litju/DynamisScience/pull/6) |
| RES-756 | Shared navigation, library and interaction preferences | [#5](https://github.com/Litju/DynamisScience/pull/5) |
| RES-757 | Research and data journeys | [#7](https://github.com/Litju/DynamisScience/pull/7) |
| RES-758 | Workbench, archive and reports | [#8](https://github.com/Litju/DynamisScience/pull/8) |
| RES-759 | Operations and measured spatial views | [#9](https://github.com/Litju/DynamisScience/pull/9) |
| RES-761 | Data workspace, specialist details and preferences | [#10](https://github.com/Litju/DynamisScience/pull/10) |
| RES-760 | Windows qualification and layout corrections | [#11](https://github.com/Litju/DynamisScience/pull/11) |

RES-621 retains the rejected baseline and controlling owner workflow. RES-613 retains installed product acceptance. The application-wide transformation remains open until the owner has independently used the current build.
