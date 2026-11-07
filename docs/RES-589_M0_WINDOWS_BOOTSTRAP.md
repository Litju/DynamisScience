# RES-589 M0 — Windows machine bootstrap

**Executed:** 2026-11-06 · **Result:** M0 environment gate passed. RES-589 remains open; this does not complete its secure-pilot or practitioner-validation gates.

## Checkout and restore decision

- Repository: `D:\projects\DynamisScience`, branch `main`, commit `f9d823d791758ad944f1dad4cbdeda29a50a8c29`, origin `https://github.com/Litju/DynamisScience.git`. The commit matches the M0 specification. No push was made and the proprietary `LICENSE` is unchanged.
- No original `E:\Data\Datasets\DynamisScience` tree or `research.db` was present. The machine exposes C: and D:, has no SMB mappings, and connected Google Drive searches for `DynamisScience`, `research.db`, and `DynamisScience backup` returned no files.
- A fresh private root was created at `D:\datasets\DynamisScience`, outside Git. Its ACL disables inherited access and grants full access to the current user, SYSTEM and local Administrators. The source files, extracted participant-level CSVs, snapshots, SQLite store, reports and receipts remain there.
- Before changing storage paths, the ignored repository-local `data/` tree was inventoried at 48 files and 4,400,781 B. Its three legacy admission snapshots and uploaded files are labelled `SRC-FIXTURE` / `FIXTURE_ONLY`; the remaining outputs are synthetic fixtures. No files were moved or deleted.
- Historical projects, studies, monitoring programs, run/evidence/report IDs and the original SQLite database were **not transferred**. The local M0 project and its run are new records created on 2026-11-06. Sequential IDs in a fresh store can overlap IDs from the unavailable database; do not merge the two histories without an explicit reconciliation.
- Repository changes add a safe MoveSmart extractor and tests, a Performance OS browser smoke script, a read-only SQLite checker and this report. Existing source metadata and the RES-587 closure now describe the unrelated personal DOCX without its filename. No source archive, participant row, SQLite database, local report or screenshot is in Git; no application design or scientific algorithm changed.

## Rights verification and admission

Live publisher metadata and file checksums were rechecked on 2026-11-06. The per-machine receipt, download times, archive preflight, snapshot IDs and Parquet checksums are in `D:\datasets\DynamisScience\manifests\res589_m0_source_verification.json`. The code catalogue retains its earlier 2026-11-04 source-assessment timestamp; the local receipt records this machine's current rights check and acquisition times.

| Dataset | Rights and source file | Verified file integrity | Admission |
|---|---|---|---|
| Holmberg Sprint Priming, [Mendeley Data v1](https://data.mendeley.com/datasets/6p99569x66/1), DOI `10.17632/6p99569x66.1` | CC BY 4.0; `DATA.xlsx`, 40,973 B | Publisher and local SHA-256: `81e5665cb9c547f8a1870a62bca87126db58108cf65e002b1fdf681deb21a9da` | `DS-REAL-MENDELEY-2C44490E08AD`, `ADMITTED_WITH_WARNINGS`; 21 subjects, 168 long measurements, 82 CMJ observations, 168 sprint observations |
| MoveSmart, [Zenodo v1.0](https://zenodo.org/records/17376717), DOI `10.5281/zenodo.17376717` | Open; CC0 1.0; `Dataset.zip`, 166,259,083 B | Publisher MD5 `cc354ea010f622572a24ccd3e6dfd5a9`; local SHA-256 `2591b9afc36bd84060fb2ca524b379ea50e67577abf02b5f88b3132635c80fb9` | `DS-REAL-MOVESMART-805259588272`, `ADMITTED_WITH_WARNINGS`; 10 subjects, 398 matched trials, 5,890,000 force samples, 453,403 IMU samples, 5 activities |

MoveSmart ZIP preflight checked 3,564 entries and 676,083,934 expanded bytes. It found zero traversal paths and zero symlinks. The checked extractor wrote only 1,769 CSV research files (675,544,106 B); it excluded `__MACOSX`, `.DS_Store` and the unrelated personal DOCX without decompressing or analysing that document. The original verified ZIP remains under the private root's restricted ACL.

Both datasets are pseudonymous. Mendeley contains derived scalar measurements, not raw CMJ traces; its single-arm design does not support a concurrent-control causal claim, and two fourth-occasion CMJ values are missing. MoveSmart contains no CMJ task and no verified sample-level IMU/force clock synchronisation; only 120 of 398 matched trials have all three force plates, and no calibration log is deposited. The independent body-weight recovery check was rejected (bias −169 N, −22.9%). Those limitations and the admission warnings remain visible in the saved manifests.

## Storage and local runtime

| Location | Actual logical bytes | GB | GiB |
|---|---:|---:|---:|
| Repository, including `.git`, `node_modules`, `.venv` and `.next` | 1,880,250,681 | 1.880 | 1.751 |
| `.git` | 28,591,861 | 0.029 | 0.027 |
| `node_modules` | 694,268,111 | 0.694 | 0.646 |
| `services/science/.venv` | 710,051,457 | 0.710 | 0.661 |
| `apps/web/.next` production build | 412,232,086 | 0.412 | 0.384 |
| Private data root, including sources, extraction, snapshots, SQLite and reports | 904,764,885 | 0.905 | 0.843 |

The source archives (`166,300,056 B`) plus filtered extracted CSVs (`675,544,106 B`) total `841,844,162 B`; this is a baseline sum, not a measured maximum disk-usage peak. The maximum temporary peak was not instrumented. The final private-root usage was measured at `904,764,885 B` (`0.843 GiB`), below the 2 GiB target by 1.157 GiB and below the 3 GiB review threshold by 2.157 GiB. D: had 45,549,772,800 B free before the work and 43,396,026,368 B free after it; C: has 22,683,594,752 B free after R installation.

The separate core installation footprint (repository, private data, R, Python, Node and Playwright browser) is 4,084,504,681 B (4.085 GB / 3.804 GiB). Including the measured shared `uv`, pnpm and npm caches gives a conservative logical path sum of 5,450,177,353 B (5.450 GB / 5.076 GiB); current free space above is the physical-disk measurement.

| Separate runtime/cache path | Actual bytes |
|---|---:|
| R 4.6.2 installation (includes lme4 binaries) | 231,391,194 |
| System Python 3.12.10 | 156,270,596 |
| uv-managed Python 3.12.13 | 59,657,073 |
| Node.js runtime | 99,342,780 |
| Playwright browser cache | 752,827,472 |
| uv package cache | 660,491,285 |
| pnpm home/store | 694,369,117 |
| npm cache | 10,812,270 |

| Runtime | Verified installation |
|---|---|
| Python / uv | System Python 3.12.10; science `.venv` Python 3.12.13; uv 0.11.25; `uv sync --locked` checked 49 packages |
| Node / pnpm | Node 22.22.2; pnpm 11.24.0; `pnpm install --frozen-lockfile` was already up to date across four workspace projects |
| R | R 4.6.2 and lme4 2.1.0; the per-user CRAN installer matched publisher MD5 `d01b7413cce5540a35eaf8295ef32197` |
| Browser | Playwright Chromium 156.0.8078.4 at `D:\SWE_HOME\ms-playwright` |

User environment settings now point to `DYNAMISSCIENCE_DATA_ROOT=D:\datasets\DynamisScience`, `DYNAMISSCIENCE_RSCRIPT=%LOCALAPPDATA%\Programs\R\R-4.6.2\bin\x64\Rscript.exe`, `R_ENVIRON_USER=%LOCALAPPDATA%\R\Renviron`, `NEXT_PUBLIC_SCIENCE_API_URL=http://127.0.0.1:8000`, `DYNAMISSCIENCE_SCIENCE_API=http://127.0.0.1:8000`, `DYNAMISSCIENCE_BROWSER_BASE=http://127.0.0.1:3001`, and `PLAYWRIGHT_BROWSERS_PATH=D:\SWE_HOME\ms-playwright`. The R environment file sets a Windows-compatible C locale; Rscript and lme4 run without startup warnings.

## SQLite and persistence evidence

The original store was absent. The existing `researchstore._ensure_schema` path created a fresh schema at `PRAGMA user_version=1`, in WAL mode with foreign keys enabled. Before any user-authored record, the new database had 16 empty application tables. `PRAGMA integrity_check` returned `ok`; `PRAGMA foreign_key_check` returned no violations.

For an end-to-end persistence check, the new database now contains one explicitly labelled M0 verification project, one Mendeley study and one synthetic monitoring program. The study ran MixedLM on 82 observations, promoted evidence, linked lineage to the Mendeley snapshot, and froze report version 2. The synthetic monitoring schedule is labelled as a local verification record, not a transferred athlete program. IDs and the HTML export are recorded under `D:\datasets\DynamisScience\reports\res589`.

The API rejected a stale project write, a frozen cohort edit and a frozen plan edit with HTTP 409. `pnpm data:generate` then regenerated the 28-athlete synthetic fixture; the SQLite project, study, monitoring program, run, evidence, report and 23 audit rows remained unchanged. After stopping and restarting the science service, all records and the frozen report reopened with the same IDs and content hash. A second integrity check remained `ok` with zero foreign-key violations.

## Qualification and product checks

- `QUAL-REAL-MIXEDLM`: **PASS** against R 4.6.2 / lme4 2.1.0; all 9 declared comparisons passed. The 82-observation log likelihood was −208.3118003 in both implementations, within the 0.001 tolerance.
- `QUAL-REAL-RELIABILITY`: **PASS** against the independent NumPy ANOVA calculation; walking ICC(3,1) 0.9511168, typical error 49.7110 N. The balanced analysis uses the first five trials for nine participants.
- `QUAL-REAL-SIGNAL`: **PASS**, 4/4 representative force-signal peak and impulse re-derivations matched. The record retains the stated four-trial scope limitation.
- Regression: `pnpm test` passed 35 web and 91 Python tests with a separate empty test data root. One Starlette/httpx deprecation warning was emitted by the test client. `pnpm lint`, `pnpm typecheck` and `pnpm build` passed. Keep test data isolated: one endpoint test expects only synthetic qualification records, while the private root now also contains the real-data qualification records.
- Real-data browser validation passed at 1440×900, 1280×800 and 1024×800: all admission, snapshot, Mendeley, MoveSmart and report markers were visible, with zero console/page errors, failed requests or horizontal overflow.
- `services/science/scripts/performance_os_smoke.py` passed the synthetic **Today → Athlete 360 → Plan → Monitor → Test → Research → Report** route sequence at 1440×900, with zero browser errors or overflow. A separate browser check opened the new Mendeley study and exported its frozen report with the embedded manifest and evidence ID.

The science API is running on `http://127.0.0.1:8000` and the production Performance OS frontend on `http://127.0.0.1:3001`, both bound to loopback.

## Reproduction commands

```powershell
$env:DYNAMISSCIENCE_DATA_ROOT = 'D:\datasets\DynamisScience'
$env:DYNAMISSCIENCE_RSCRIPT = Join-Path $env:LOCALAPPDATA 'Programs\R\R-4.6.2\bin\x64\Rscript.exe'
$env:R_ENVIRON_USER = Join-Path $env:LOCALAPPDATA 'R\Renviron'
$env:NEXT_PUBLIC_SCIENCE_API_URL = 'http://127.0.0.1:8000'
$env:DYNAMISSCIENCE_BROWSER_BASE = 'http://127.0.0.1:3001'
$env:PLAYWRIGHT_BROWSERS_PATH = 'D:\SWE_HOME\ms-playwright'

uv sync --locked --directory services/science
pnpm install --frozen-lockfile
pnpm data:generate

pnpm test

pnpm lint
pnpm typecheck
pnpm build

uv run --directory services/science playwright install chromium
uv run --directory services/science python -m scripts.sqlite_integrity
uv run --directory services/science python -m scripts.browser_validation
uv run --directory services/science python -m scripts.performance_os_smoke

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$backup = Join-Path $env:DYNAMISSCIENCE_DATA_ROOT "backups\research-$stamp.sqlite3"
$restore = Join-Path $env:DYNAMISSCIENCE_DATA_ROOT "tmp\restore-$stamp"
uv run --directory services/science python -m scripts.sqlite_recovery backup --destination $backup
uv run --directory services/science python -m scripts.sqlite_recovery verify --database (Join-Path $env:DYNAMISSCIENCE_DATA_ROOT 'research\research.db')
uv run --directory services/science python -m scripts.sqlite_recovery restore --backup $backup --destination-root $restore
uv run --directory services/science python -m scripts.sqlite_recovery verify --database (Join-Path $restore 'research\research.db')
```

`services/science/tests/conftest.py` now replaces any inherited operational root before collection and confines tests to a temporary root; the normal `pnpm test` command needs no manual environment cleanup. The `pnpm dev` command starts the API at `127.0.0.1:8000` and frontend at `127.0.0.1:3001`.

For a fresh source admission, create the two `sources` folders beneath the configured root, download the exact files from the publisher URLs recorded in `real_sources.py`, compare their current publisher checksums, then run:

```powershell
uv run --directory services/science python -m dynamis_science.extract_movesmart
uv run --directory services/science python -m dynamis_science.ingest_real --source all
```

Run the compatible real-data analyses through `POST /analyses/execute` before `uv run --directory services/science python -m dynamis_science.qualification_real`.

## Post-M0 engineering hardening — 2026-11-07

### Starting audit

- The checkout started on `main` at `f9d823d791758ad944f1dad4cbdeda29a50a8c29`, with origin `https://github.com/Litju/DynamisScience.git` and exactly the seven M0 local changes listed above. No other tracked or untracked work was present. Ports 3001 and 8000 had no listeners.
- `D:\datasets\DynamisScience` existed with its restricted ACL and 1,829 files totaling `904,764,885 B`. Its SQLite store was schema v1, WAL mode, 16 tables, 1 project, 1 study, 1 monitoring program, 1 run, 1 evidence record and 23 audit records; integrity was `ok` with zero foreign-key violations.
- The ignored repository `data/` inventory was 48 fixture-only/synthetic files totaling `4,400,781 B`. It was left in place; nothing was moved or deleted.

### Completed hardening gates

- **Storage authority:** legacy `/admission/*`, Mendeley, MoveSmart, research SQLite, and Performance OS persistence now resolve through the validated `DYNAMISSCIENCE_DATA_ROOT`. It must be an absolute directory outside the checkout. There is no repository-local fallback for private data. Existing ignored fixture-only repository data was not migrated.
- **Test isolation:** `tests/conftest.py` sets a temporary root before test collection, protects the inherited operational path, and rejects non-temporary storage during pytest. A nested pytest run against a disposable simulated operational root verified sentinel, SQLite, WAL and SHM hashes stayed unchanged. The legacy performance-store override is ignored.
- **Development network:** the root development command fixes both binds to loopback (`127.0.0.1:8000` and `127.0.0.1:3001`). Windows listener inspection showed only those addresses. `/health` returned `ok`; all checked frontend routes returned 200; browser requests had no failures.
- **SQLite recovery:** `scripts.sqlite_recovery` uses SQLite Online Backup API, checkpoints the backup into a standalone file, verifies its logical database hash and all row counts, restores to a new private `tmp/` root, and reopens it through `researchstore`. The final private backup is `D:\datasets\DynamisScience\backups\research-res589-final-20261107T044500Z.sqlite3` (233,472 B, no WAL/SHM sidecars). The restored database matched schema v1, all 16 tables, all row counts and the source logical hash; the app reopened 1 project, 1 study, 1 monitoring program, 1 run and 1 evidence record, with a 10-node lineage. Original database/WAL/SHM hashes were unchanged.
- **M0 privacy and operations:** current source and documentation describe the excluded unrelated personal DOCX generically and omit sample participant folder values. The extractor rejects traversal, symlinks and an unexpected expanded-size inventory, and it excludes unrelated documents. Current local instructions describe storage, runtime prerequisites, test isolation, backup/recovery and the distinction between loopback development and a separately authenticated pilot. No GitHub push or history rewrite was made.

### Final verification

- `pnpm test`: **35 web + 101 Python tests passed**; one existing Starlette/httpx deprecation warning.
- `pnpm lint`, `pnpm typecheck` and `pnpm build`: **passed**.
- Synthetic Performance OS browser smoke: all seven routes plus Athlete 360 passed at 1440×900, with zero console/page/network errors and no overflow.
- Real-data browser validation: admission, snapshots, both source studies and reports passed at 1440×900, 1280×800 and 1024×800; zero browser errors, failed requests or horizontal overflow.
- The Mendeley evidence/report smoke returned one evidence record, a 10-node lineage and an HTML export containing the manifest and evidence reference.
- Re-running real qualification on the restored copy first reported blocked because the restored research database had no legacy real-analysis run records and the copy lacked the raw signal files needed for independent re-derivation. The existing Mendeley trend and MoveSmart reliability methods were then executed against the already-admitted snapshots; eight original force CSVs (5,064,990 B) required for the four representative signal trials were copied into the private verification root. The rerun passed all 9 MixedLM comparisons, the MoveSmart ICC/typical-error/CV comparisons and all 4 signal re-derivations. No data was re-downloaded and no scientific algorithm changed.
- The private root now measures `1,032,104,990 B` (`0.961 GiB`), including private backup and verification copies, below the 2 GiB target. D: has `42,918,014,976 B` free.

Local commits completed for the storage, isolation, listener, recovery and performance-store gates: `4e809ac`, `ab96317`, `252e0c1`, `22a10d6`, `60b0938`, and `7b51a50`. All reference RES-589. No GitHub push was made.

## Remaining limits

This is a fresh local installation, not a full cross-device history transfer. The missing original SQLite history and reports remain unavailable, and new sequential run IDs may overlap IDs in that missing store. No merge or overwrite was attempted. The unrelated filename remains in the already-published historical baseline because history was not rewritten; current source and docs omit it. Authentication, authorization, cross-organization isolation, pilot security/deployment qualification, and external-practitioner validation remain the parent RES-589 gates; M0 and this hardening pass do not mark the issue Done or claim pilot readiness.
