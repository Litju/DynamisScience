# RES-613 Native Desktop Acceptance — working evidence

Status: **not accepted; owner review and remaining checks required**. No external practitioner validation is claimed (RES-589 remains separate).

## Baseline and isolation

- Starting HEAD `e7cff2f989bbe066e612ee72567011db2976d884`; RES-604 installer SHA-256 verified as `17C04C46F882690EDF49FA799DCD958C89938EEE0959CF9621E7AB0166889B2F`.
- All GUI writes were made to synthetic data or checksum-verified copies under `D:/DynamisScience-RES613-audit`. Three private `*.db` files were hashed before and after and matched; this is not a fingerprint of every file in the private root. The pre-existing generator manifest SHA-256 remained `835398DA594421BC9F04647992B0E9CEFD5DC844FD931D1964896B2E164A2587`.
- Windows display: one 1366×768 screen, 1366×720 work area. Qt `QT_SCALE_FACTOR=1.5` was used for a process-level high-DPI check; a second physical monitor and live scale changes were not available.

## Findings and repairs

| Severity | Workflow and reproduction | Expected / observed | Root cause and disposition |
|---|---|---|---|
| P1 | Run Mendeley; switch to MoveSmart | New context must not show previous analysis. Old result text and plot remained after state reset. | View widgets were not reset. `93bcad7` and `836b561` clear results, inputs, dataset/cohort and report views; GUI switch and targeted tests passed. |
| P1 | Run reference Mendeley analysis → promote → cite | Citation should persist. `ResearchNotFound` was shown. | Citation facade incorrectly routed reference studies to authored-study storage. `820c3a1` routes to real-store citation and rejects nonexistent artifacts; GUI and copied-data test passed. |
| P1 | Open run provenance | Node names should be visible. Graph showed blank boxes. | Graphics text wrappers were discarded. `6c8afa5` retains labels; native graph and scene test passed. |
| P1 | Open analysis at 1366×768 and request figure | Controls and labels should remain legible. Window expanded beyond screen, parameter field collapsed, and split plot labels overlapped. | Fixed controls imposed excessive width; plot shared narrow space. `d70ccc4`, `0bd1c62`, `eb1a128` fit initial window, arrange controls and provide a full-width figure tab. Native aggregate MixedLM figure was inspected; at small heights labels remain compact. |
| P1 | Export the MixedLM diagnostic | The Q–Q axis and label must describe the values. The original identity line extended the theoretical axis to the residual extremes and called marginal residuals standardized. | `realanalysis.py` subtracts only fixed effects, then divides by the conditional residual SD. `870b488` labels that quantity as marginal and exploratory, removes the inappropriate identity line, and allows the theoretical axis to follow its own data. The calculation and stored result digests remain unchanged; a conditional-residual diagnostic is not supplied. Statsmodels describes its `MixedLMResults.resid` as incorporating predicted random effects: https://www.statsmodels.org/stable/generated/statsmodels.regression.mixed_linear_model.MixedLMResults.resid.html. |
| P1 | Open study / Today with 150% Qt scaling | Workspace should remain reachable. The window extended beyond the screen. | Minimum sizes exceeded available work area. `e2373ec`, `043e318` add scrolling for compact startup screens and retain normal proportions. Verified on one display; changing screens after startup remains untested and does not reevaluate layout. |
| P2 | Performance Today context | Full movement limitations should be readable. Text was cut off. | Labels lacked wrapping. `339d86c` wraps warnings; native synthetic view verified. |
| P2 | Screen-reader tree → Performance rail | Each navigation control should have a name. The controls were unnamed. | Composite buttons had no accessible name. `6a46352` names them; Windows accessibility tree and test verified. Full screen-reader evaluation remains outstanding. |
| P2 | Compose practitioner report → preview | A practitioner should read the report. Preview displayed raw JSON. | `1d894ee` reuses the HTML renderer and a Qt-compatible metric table; native preview inspected. |
| P1 | Admit local file → run QC | The decision and warnings should be readable before admission. The QC output pane collapsed to one line. | `4a74b40` reserves 100 pixels for the summary. The native dialog and targeted admission test were checked. |
| Test harness | Run packaged real qualification on Windows PowerShell 5 | Three qualified results should pass. The first two smoke attempts failed despite three `QUALIFIED` records. | PowerShell wrapped the JSON array as one item. `cc23a92` fixes parsing; the subsequent full package smoke passed for build `836b561`. |

## Observed workflows

- Native first-run folder picker accepted an isolated folder; restart reopened it without another prompt on the RES-604 installed release.
- Native synthetic project and study were created. Initial cohort and plan froze; each was forked to a new draft and persisted in the isolated store. A four-row test-only CSV was registered and QC quarantined it because its declared calibration was `SIMULATED`; the quarantine was recorded. The GUI did not admit it as calibrated data. Successful admission was exercised by the automated suite but not repeated manually. In the GUI, the synthetic cohort and plan forks were frozen, the study made ready, descriptive analysis executed, and the result promoted and cited; report version 2 was frozen, exported as HTML, and reopened in the final installed application. The report did not contain model-based inference.
- On verified real-data copies, the native GUI completed Mendeley MixedLM, MoveSmart reliability and signal QA. MixedLM displayed an estimate and interval plus an exploratory marginal Q–Q plot; reference evidence promotion, citation and the lineage graph were exercised. MoveSmart signal diagnostics explicitly state that device clocks differ and sample-level synchronization is not claimed. PNG, rendered PDF and rendered SVG from the copied-data regression were visually inspected after the diagnostic-label correction.
- Synthetic Performance OS Today, Plan, Monitor, Test, Research, Report, Athlete 360 and Match/Pose were inspected across the audit. A session of 75 min × RPE 6 appeared as 450 AU; a synthetic coach report was composed, frozen, exported and reopened in the native report view. Match/pose is labelled synthetic and bounded. Automated Qt tests exercise plan publication, notes, reliability, report operations and persistence.
- Mendeley's publisher page identifies version 1 as CC BY 4.0: https://data.mendeley.com/datasets/6p99569x66/1. The checked-in system design describes a different MoveSmart license from the copied source manifest. The application showed CC0-1.0, matching the manifest's recorded Zenodo metadata; the Zenodo record was not accessible during this audit, so reconcile the historical design document and current source record before relying on that rights claim.

## Evidence and remaining work

Screenshots and package measurements are retained in the audit folder. The browser security policy refused opening the local exported HTML, so standalone browser rendering of the exported report was not independently verified. The 150% compact view requires substantial horizontal and vertical scrolling; long lineage labels may overflow their boxes, and reference-study report version freezing remains available only for authored studies. The research overview and several result inspectors still expose JSON. Keyboard traversal, screen-reader use, common resolutions beyond this display, multi-monitor transitions, failure states and the complete installed-app authoring/admission journey are not fully qualified.

The full source suite passed at application commit `4a74b400d6ed22392040e7b01def976d5fd440fa`: **93 passed in 118.93 seconds**. The source-matched installer was built as `res604-20261109-083803-15e14ac9`, application version 0.1.0, SHA-256 `EDC4553EB9EA9A158645226F564D9207F4E25E2097B1057DEFDD32D65202F1D8`, 141,528,685 bytes. Its source stamp records the pre-existing manifest change and diff SHA-256 `D0691F70663717FC86A4D9AB51AD62650903F0F3D19AB21457FABEB593DDBF4B`. Final installed-package smoke passed: all three real methods were QUALIFIED and their packaged digests matched direct execution; PNG/PDF/SVG carried provenance; SQLite integrity was `ok`, backup and restore preserved the logical hash, and the database survived uninstall. The installed catalogue started in 1,973 ms with 119.41 MiB peak working set; the synthetic Performance view started in 2,774 ms with 245.77 MiB peak working set. No listeners were detected. These are individual measurements, not benchmark distributions. The final installer was then installed into an isolated directory and the frozen synthetic study report reopened in its native window. Owner review and explicit sign-off remain required; do not mark RES-613 Done.

## Privacy-safe visual evidence

These screenshots were captured at the stated intermediate application commits; the final build incorporates those changes. The plots and study lineage use aggregate data from the verified copies; the Performance views use synthetic fixtures.

- [Normal desktop workspace](res613-evidence/normal-final.png)
- [150% scaling](res613-evidence/high-dpi.png)
- [Native report preview](res613-evidence/report-preview.png)
- [Provenance graph](res613-evidence/lineage.png)
- [MixedLM diagnostic exported to PDF and rendered](res613-evidence/mixedlm-export.png)
- [Synthetic match and pose](res613-evidence/match-pose.png)
