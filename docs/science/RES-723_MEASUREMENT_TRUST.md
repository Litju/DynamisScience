# RES-723 Measurement trust and individual change

In an individual investigation, open **Analysis → Measurement trust and individual change**. Choose a reference session and a comparison session on the active data revision. The reference can come from an earlier revision. An earlier attachment without confirmed identity continuity yields an incomparable assessment. The first version supports CMJ jump height in cm from admitted summary trials.

Use **Review matched retest evidence** to select two other sessions on the active revision. Record the testing log or protocol reference, the common jump-height scoring method, the applicable population, and who checked the stable retest conditions. The method requires the same instrument, protocol, sampling rate, recorded day interval and trial aggregation. It uses complete pairs from other athletes and lists exclusions. Scoring comparability, retest conditions and applicability rely on the recorded researcher review.

**Results** shows the two session scores, missing and excluded trials, observed change, and what the evidence supports. **Source trials** lists the saved trial IDs and source artifacts. If the captured revision has a linked force recording, the trace opens only for an unambiguous athlete, session and trial match with verified Parquet checksums. **Diagnostics and provenance** retains the QC records, source and Parquet hashes, retest scores, assumptions and execution version.

| Assessment | Meaning |
| --- | --- |
| Interpretable | A reviewed, matched retest supports comparison with its expected repeat differences. |
| Incomparable | Identity, session, units, acquisition or QC prevents a defensible comparison. |
| Not estimable | A session score is incomplete or applicable between-session error is unavailable. An observed difference may still be reported. |
| Unqualified | Source verification failed or the nominated retest evidence does not support the comparison. |

For independent complete athlete pairs, the retest scores are session means. The method reports the mean and sample SD of the paired differences, consistency ICC(3,1), typical error under equal independent session errors, and the conventional MDC95. The interpretation uses a 95% Student-t prediction range centered on the retest bias and includes estimation uncertainty from the finite reference sample. It assumes approximately normal reference differences and comparable variability for the reviewed population and athlete. Repeatability can include short-term biological variation. The assessment does not establish meaningful change, fatigue, adaptation, readiness, injury risk or causation.

The earlier assessment stays in Results after a correction. A new assessment on a changed revision receives a new run and preserves its own provenance. To reassess an older comparison revision, select that data revision in workspace history before running.

Run the independent arithmetic checks and the executable 20-athlete native journey from `services/science`.

```powershell
.venv/Scripts/python.exe scripts/scoped_tests.py tests/test_measurement_trust.py tests/test_native_measurement_trust.py
```
