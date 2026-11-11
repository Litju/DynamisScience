# RES-636 qualification — one-click scientific import

Engineering record, not product acceptance. RES-613 remains the owner acceptance gate. **RES-636 is not complete:** the vendor-adapter acceptance item is blocked (see Gate 5).

## What was built

`dynamis_science/importer.py` is a thin front end over the existing `admission.py` (unchanged). Flow: probe (CSV UTF-8/BOM with delimiter sniffing, Parquet, bounded non-recursive folders) → propose mapping from headers and bracketed units with confidence and explicit ambiguity → deterministic normalization to canonical names and units → get-or-create source/instrument/protocol (a registered record is never silently changed) → ingest the normalized Parquet as a source artifact → existing QC → existing admit and snapshot. `desktop/import_review.py` is the single review screen (Research → Import data…, Ctrl+I; drag and drop). The raw file is kept unchanged with an import receipt (raw SHA-256, schema fingerprint, mapping, ignored columns).

Never invented: subject and trial identity, session, sampling rate, calibration, rights, force orientation. Session and sampling rate come from the file or the researcher. Unsupported or unstated units are review items. TEST_FIXTURE data are admitted only as SYNTHETIC_ONLY; real claims still need verified rights and a CALIBRATED instrument.

Adapter contract (module functions, no registry): `probe_file` (detect) → `propose_generic` / `edit_mapping` (propose) → `normalize` → `stage` (existing QC) → `admit` / `quarantine`.

## Commits (local, unpushed)

| Commit | Change |
| --- | --- |
| `b29af8a` | Importer core and tests (detection, mapping, units, presets, staged admission, folder bounds, duplicates). |
| `92db733` | Native review screen, menu entry, raw force-time hold, Qt tests. |
| `1b56305` | QC-versus-admission wording, walkthrough script, screenshots. |
| this commit | Blank CSV lines are not records; this record and the frozen-app screenshots. |

## Gate results

| Gate | Result |
| --- | --- |
| 1 Detection | CSV/Parquet/folder implemented and tested. Unknown or ambiguous input yields a review state with the reason. |
| 2 Normalization | Units: kg/g/lb, cm/m/mm/in, s/ms, N/kN, Hz, N·s/kg, W/kg. Existing QC reused; no second ETL. |
| 3 Presets | Versioned, keyed to a schema fingerprint of names and dtypes. Same fingerprint reuses mapping and context and QC runs automatically; Admit stays an explicit click. Any header or dtype change (including a unit in a header) is drift and is reviewed. Rights are never reused from a preset: an unverified source needs a fresh rights review. |
| 4 Review screen | Preview, mapping decisions, detection, QC verdict, warnings, provenance and storage outcome; Admit, Edit mapping, Quarantine, Save preset. Fits a 910×512 logical desktop (1366×768 at 150%); controls have accessible names. |
| 5 Vendor interoperability | **BLOCKED.** See below. |
| 6 Verification | See below. |

### Gate 5 — vendor adapter

VALD's support pages (read 2026-11-11) document a ForceDecks Windows raw export containing summary information, "Raw Time (s)", "Left Force (N)" and "Right Force (N)", written as a per-athlete CSV. They do not publish the exact CSV headers, the summary-block layout, the sampling rate, zeroing or orientation. Hawkin documents a time / left / right / combined force layout at 1000 Hz with no exact headers or units, and no sample rows. No authorized or sanitized sample exists in the repository, and admission has no raw-trace family. Raw force-time files are therefore recognised and held (UNSUPPORTED with the reason; tested) rather than mapped, and **no vendor compatibility is claimed**. Vendor-computed versus DynamisScience-derived metrics are not yet separated because no vendor adapter exists. To proceed: an authorized ForceDecks or Hawkin export (raw and results) and a decision on a raw-trace admission family.

### Gate 6 — evidence

- Importer and review tests: 24 passed. Full source regression at `1b56305`: **212 passed in 207 s** (offscreen, temporary roots). The blank-line fix postdates that run; the 24 importer/Qt tests were re-run after it.
- Native walkthrough (`scripts/res636_walkthrough.py`, real `MainWindow` on the Windows platform, disposable root, screenshots and `receipt.json` in `res636-evidence/`): unknown file review; QC verdict SYNTHETIC_ONLY; admit; preset save; repeat import with preset (QC already run); schema drift; invalid file REJECTED then quarantined with no snapshot; folder; raw force-time held; admitted snapshots visible in the existing workbench catalogue (units cm, kg, N, Hz; SYNTHETIC chip) and readable through `read_table_page`.
- Duplicate protection: renamed copy of identical content is not admitted again; identical file re-import is idempotent; same basename in different sources gives distinct snapshots.
- Packaged app: `build_windows.ps1 -TestIdentity` built from source `1b56305162a9a681cba90918dbab9fc1d931aa05` (tree dirty only by the owner's manifest). `DynamisScience.exe` SHA-256 `F957B7608B7B7B0035B4C1E35237529269A7ED6FCE3107B1BBE56F60F742DEBD`; test installer `DynamisScience-RES621Test-Setup-x64.exe` SHA-256 `AD69BCAA7DA7DAA8A25576A5B6F5C6F9FA32ADF7E1EA0910EF1CAD12FFED9CCE` (142,807,530 bytes; not installed). The frozen executable was started with a disposable `--data-root`, Research → Import data opened with Ctrl+I, and a CSV was loaded through the native file dialog (`frozen-*.png`). The frozen run showed a trailing blank line counted as a record; fixed afterwards in source, so the shipped package predates that fix. **The frozen app was not driven through QC, Admit or Quarantine**; those are verified from source only.

### Data preservation

- `data/synthetic/generator_manifest.json` SHA-256 `835398DA594421BC9F04647992B0E9CEFD5DC844FD931D1964896B2E164A2587` before and after; still uncommitted.
- Operational private root `D:\datasets\DynamisScience`: never configured as a data root by any run here (tests refuse an inherited root; the walkthrough and frozen run used new temporary roots, deleted afterwards). Metadata fingerprint taken after the work (1929 files; SHA-256 over path, size and mtime) `AF914E72BB4A1A192854B82405E8FFEDC71912DC9243AD73A26204DC0F459413`. No "before" fingerprint exists, so this is not proof of non-modification.

## Known limits

Trial identifiers must be unique per file (admission rejects repeats), so exports that number trials per athlete need a composite identifier. Folders are non-recursive with at most 100 files of 256 MiB; files are read whole into memory (no streaming). Cancel is not offered during QC. Staging registers source, instrument and protocol and stores the source artifact before the researcher presses Admit (as the existing admission dialog does). Windows only.
