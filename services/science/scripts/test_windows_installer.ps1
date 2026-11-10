$ErrorActionPreference = "Stop"
$serviceRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$sourceDataRoot = if ($env:DYNAMISSCIENCE_DATA_ROOT) { $env:DYNAMISSCIENCE_DATA_ROOT } else { "D:\datasets\DynamisScience" }
if (-not (Test-Path -LiteralPath (Join-Path $sourceDataRoot "research\research.db"))) {
    throw "Verified Mendeley/MoveSmart source data is required for packaged scientific regression."
}
$packagingRecord = Get-ChildItem -LiteralPath (Join-Path $serviceRoot "build") -Directory |
    Where-Object { $_.Name -like "res604-*" } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $packagingRecord) { throw "Run build_windows.ps1 before installer verification." }
$installer = Join-Path $packagingRecord.FullName "dist\installer\DynamisScience-Setup-x64.exe"
$unpackedExe = Join-Path $packagingRecord.FullName "dist\DynamisScience\DynamisScience.exe"
if (-not (Test-Path -LiteralPath $installer) -or -not (Test-Path -LiteralPath $unpackedExe)) {
    throw "The PyInstaller bundle or Inno Setup installer is missing."
}
$packagingMeasurements = Get-Content -LiteralPath (Join-Path $packagingRecord.FullName "packaging-measurements.json") -Raw | ConvertFrom-Json
if ($packagingMeasurements.source_commit -notmatch '^[0-9a-f]{40}$' -or -not $packagingMeasurements.source_diff_sha256) {
    throw "The package does not record an exact source commit and working-tree fingerprint."
}

$testRoot = Join-Path $env:TEMP ("dynamis-g4-installer-" + [guid]::NewGuid().ToString("N"))
$onedirDataRoot = Join-Path $testRoot "onedir-data"
$installedDataRoot = Join-Path $testRoot "installed-data"
$realDataRoot = Join-Path $testRoot "isolated-real-data"
$installRoot = Join-Path $testRoot "installed-app"
$benchmarks = [ordered]@{
    platform = [System.Environment]::OSVersion.VersionString
    source_commit = $packagingMeasurements.source_commit
    source_status = @($packagingMeasurements.source_status)
    source_diff_sha256 = $packagingMeasurements.source_diff_sha256
    installer_path = $installer
    installer_sha256 = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash
    runs = @()
    network_listeners = @()
}
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$env:QT_QPA_PLATFORM = "windows"
$env:DYNAMISSCIENCE_BROWSER_BASE = ""
$env:DYNAMISSCIENCE_SCIENCE_API = ""
$env:HTTP_PROXY = "http://127.0.0.1:9"
$env:HTTPS_PROXY = "http://127.0.0.1:9"
$env:DYNAMISSCIENCE_SOURCE_ROOT = $sourceDataRoot
$env:DYNAMISSCIENCE_REAL_TEST_ROOT = $realDataRoot

function Invoke-PackagedSmoke(
    [string]$Executable,
    [string]$Label,
    [string]$DataRoot,
    [string]$PerformancePage = ""
) {
    $env:DYNAMISSCIENCE_DATA_ROOT = $DataRoot
    $env:DYNAMISSCIENCE_SETTINGS_FILE = Join-Path $testRoot ($Label + "-settings.json")
    $ready = Join-Path $testRoot ($Label + "-ready.txt")
    $clock = [System.Diagnostics.Stopwatch]::StartNew()
    $launchArgs = @("--data-root", $DataRoot, "--benchmark-ready-file", $ready, "--benchmark-exit-after-ready")
    if ($PerformancePage) { $launchArgs += @("--benchmark-performance-page", $PerformancePage) }
    $process = Start-Process -FilePath $Executable -ArgumentList $launchArgs -PassThru
    $peakWorkingSet = 0L
    $listeners = [System.Collections.Generic.HashSet[int]]::new()
    try {
        $deadline = [DateTime]::UtcNow.AddSeconds(180)
        while (-not (Test-Path -LiteralPath $ready) -and [DateTime]::UtcNow -lt $deadline) {
            $process.Refresh()
            if ($process.HasExited) { throw "$Label smoke process exited before catalogue readiness ($($process.ExitCode))." }
            $peakWorkingSet = [Math]::Max($peakWorkingSet, [long]$process.WorkingSet64)
            try {
                Get-NetTCPConnection -State Listen -OwningProcess $process.Id -ErrorAction Stop |
                    ForEach-Object { [void]$listeners.Add([int]$_.LocalPort) }
            } catch { }
            Start-Sleep -Milliseconds 25
        }
        if (-not (Test-Path -LiteralPath $ready)) { throw "$Label did not reach catalogue readiness in 180 seconds." }
        $clock.Stop()
        $process.WaitForExit(30000) | Out-Null
        if (-not $process.HasExited) { throw "$Label did not exit after the smoke measurement." }
        if ($listeners.Count) { throw "$Label opened listening TCP ports: $($listeners -join ', ')" }
        return @{
            label = $Label
            startup_to_catalogue_ms = $clock.Elapsed.TotalMilliseconds
            peak_working_set_mb = [Math]::Round($peakWorkingSet / 1MB, 2)
            listener_count = $listeners.Count
            process_exit_code = $process.ExitCode
        }
    }
    finally {
        $process.Refresh()
        if (-not $process.HasExited) {
            [void]$process.CloseMainWindow()
            if (-not $process.WaitForExit(3000)) { Stop-Process -Id $process.Id -Force }
        }
    }
}

try {
    $benchmarks.runs += Invoke-PackagedSmoke $unpackedExe "onedir" $onedirDataRoot

    $installerProcess = Start-Process -FilePath $installer `
        -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/DIR=$installRoot") `
        -PassThru -Wait -WindowStyle Hidden
    if ($installerProcess.ExitCode -ne 0) { throw "Inno Setup installation failed ($($installerProcess.ExitCode))." }
    $installedExe = Join-Path $installRoot "DynamisScience.exe"
    if (-not (Test-Path -LiteralPath $installedExe)) { throw "The installer did not place DynamisScience.exe in the selected install directory." }
    $requiredInstalledPaths = @(
        "_internal\PySide6\QtWidgets.pyd",
        "_internal\PySide6\QtOpenGL.pyd",
        "_internal\PySide6\QtOpenGLWidgets.pyd",
        "_internal\pyqtgraph",
        "_internal\OpenGL",
        "_internal\THIRD_PARTY_LICENSES.md",
        "_internal\THIRD_PARTY_NOTICES.txt",
        "_internal\licenses\LGPL-3.0.txt",
        "_internal\scripts\real_mixedlm.R"
    )
    foreach ($relativePath in $requiredInstalledPaths) {
        if (-not (Test-Path -LiteralPath (Join-Path $installRoot $relativePath))) {
            throw "The installer omitted required runtime content: $relativePath"
        }
    }
    if (-not (Get-ChildItem -LiteralPath (Join-Path $installRoot "_internal\matplotlib\backends") -Filter "_backend_agg*.pyd" -File)) {
        throw "The installer omitted the Matplotlib Agg backend."
    }
    $benchmarks.runs += Invoke-PackagedSmoke $installedExe "installed" $installedDataRoot
    $benchmarks.runs += Invoke-PackagedSmoke $installedExe "installed-performance" $installedDataRoot "today"

    $workerRequestPath = Join-Path $installedDataRoot "tmp\packaged-worker-request.json"
    $workerResponsePath = Join-Path $installedDataRoot "tmp\packaged-worker-response.json"
    $workerExpectedPath = Join-Path $installedDataRoot "tmp\packaged-worker-expected.json"
    $seedCode = @'
import hashlib, json, os, shutil, sqlite3
from pathlib import Path
import polars as pl
from dynamis_science.desktop.services import DynamisAppService
s = DynamisAppService()
project = s.create_project({"title": "Packaged worker smoke", "dataset_snapshot_ids": ["DS-SYNTH-001"]})
study = s.create_study(project["id"], {"title": "Worker run", "research_question": "Does the measured outcome change?", "dataset_snapshot_id": "DS-SYNTH-001", "primary_metric_id": "MET-CMJ-IMPULSE", "design": "OBSERVATIONAL_LONGITUDINAL"})["study"]
s.freeze_cohort(s.list_cohorts(study["id"])[-1]["id"])
plan = s.freeze_plan(s.list_plans(study["id"])[-1]["id"])
s.transition_study(study["id"], "READY")
payload = {"method_id": plan["method_id"], "outcome_metric_id": plan["outcome_metric_id"], "parameters": plan.get("parameters", {})}
request = {"data_root": os.environ["DYNAMISSCIENCE_DATA_ROOT"], "study_id": study["id"], "payload": payload}
run = s.execute_analysis_run(study["id"], payload)
base = Path(os.environ["DYNAMISSCIENCE_DATA_ROOT"]) / "tmp"
(base / "packaged-worker-request.json").write_text(json.dumps(request), encoding="utf-8")
(base / "packaged-worker-expected.json").write_text(json.dumps({"result_digest": run["result_digest"]}), encoding="utf-8")
(base / "figure-worker-request.json").write_text(json.dumps({"operation": "figure_export", "data_root": os.environ["DYNAMISSCIENCE_DATA_ROOT"], "output_dir": str(base / "packaged-figures"), "run": run}, default=str), encoding="utf-8")
(base / "qualification-worker-request.json").write_text(json.dumps({"operation": "real_qualification", "data_root": os.environ["DYNAMISSCIENCE_DATA_ROOT"]}), encoding="utf-8")

source_root = Path(os.environ["DYNAMISSCIENCE_SOURCE_ROOT"])
real_root = Path(os.environ["DYNAMISSCIENCE_REAL_TEST_ROOT"])
(real_root / "snapshots").mkdir(parents=True)
(real_root / "manifests").mkdir()
(real_root / "research").mkdir()
shutil.copy2(source_root / "manifests" / "admissions.json", real_root / "manifests")
for source_snapshot in sorted((source_root / "snapshots").glob("DS-REAL-*")):
    copied = real_root / "snapshots" / source_snapshot.name
    shutil.copytree(source_snapshot, copied)
    manifest = json.loads((copied / "snapshot.json").read_text(encoding="utf-8"))
    for filename, expected in manifest.get("checksums", {}).items():
        with (copied / filename).open("rb") as handle:
            if hashlib.file_digest(handle, "sha256").hexdigest() != expected:
                raise RuntimeError(f"Copied snapshot checksum failed: {copied.name}/{filename}")
source_db = sqlite3.connect(f"file:{(source_root / 'research' / 'research.db').as_posix()}?mode=ro", uri=True)
target_db = sqlite3.connect(real_root / "research" / "research.db")
try:
    source_db.backup(target_db)
finally:
    target_db.close()
    source_db.close()

os.environ["DYNAMISSCIENCE_DATA_ROOT"] = str(real_root)
from dynamis_science import realstore
real_service = DynamisAppService()
real_payloads = {
    "mendeley-trend": (realstore.STUDY_MENDELEY, {"method_id": "METH-REAL-TREND", "outcome_metric_id": "MET-REAL-CMJ-HEIGHT", "parameters": {"reference_occasion": 1, "contrast_occasion": 4}}),
    "movesmart-reliability": (realstore.STUDY_MOVESMART, {"method_id": "METH-REAL-RELIABILITY", "outcome_metric_id": "MET-REAL-FZ-PEAK", "parameters": {"activity": "Walking", "max_trials": 8}}),
    "movesmart-signal": (realstore.STUDY_MOVESMART, {"method_id": "METH-REAL-SIGNAL-QA", "outcome_metric_id": "MET-REAL-FZ-PEAK", "parameters": {}}),
}
real_tmp = real_root / "tmp"
real_tmp.mkdir(exist_ok=True)
for label, (study_id, scientific_payload) in real_payloads.items():
    scientific_run = real_service.execute_analysis_run(study_id, scientific_payload)
    request = {"operation": "analysis", "data_root": str(real_root), "study_id": study_id, "payload": scientific_payload}
    (real_tmp / f"{label}-request.json").write_text(json.dumps(request), encoding="utf-8")
    (real_tmp / f"{label}-expected.json").write_text(json.dumps({"result_digest": scientific_run["result_digest"], "method_id": scientific_run["method_id"]}), encoding="utf-8")

raw_source = source_root / "extracted" / "zenodo-17376717" / "Dataset"
if not raw_source.is_dir():
    raise RuntimeError("The verified MoveSmart raw extraction is required for qualification smoke.")
raw_target = real_root / "extracted" / "zenodo-17376717" / "Dataset"
signal_rows = realstore.read_table("DS-REAL-MOVESMART-805259588272", "signal_trials")
for activity, prefix in {"Walking": "walk", "Running": "run", "Heel drop": "heel", "Step drop": "drop"}.items():
    row = signal_rows.filter(pl.col("activity") == activity).sort(["subject_id", "trial_number"]).row(0, named=True)
    files = sorted(raw_source.glob(f"{row['participant_folder']}/{prefix}{int(row['trial_number']):04d}_f_*.csv"))
    if not files:
        raise RuntimeError(f"MoveSmart force-source files are missing for {activity}.")
    destination = raw_target / row["participant_folder"]
    destination.mkdir(parents=True, exist_ok=True)
    for source_file in files:
        target_file = destination / source_file.name
        shutil.copy2(source_file, target_file)
        with source_file.open("rb") as handle:
            source_digest = hashlib.file_digest(handle, "sha256").hexdigest()
        with target_file.open("rb") as handle:
            target_digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if source_digest != target_digest:
            raise RuntimeError(f"MoveSmart source copy check failed: {source_file.name}")
(real_tmp / "real-qualification-request.json").write_text(json.dumps({"operation": "real_qualification", "data_root": str(real_root)}), encoding="utf-8")
'@
    Push-Location $serviceRoot
    try {
        $seedCode | uv run python -
        if ($LASTEXITCODE -ne 0) { throw "Preparing disposable worker analysis data failed." }
    }
    finally { Pop-Location }
    $workerClock = [System.Diagnostics.Stopwatch]::StartNew()
    $workerProcess = Start-Process -FilePath $installedExe `
        -ArgumentList @("--worker", $workerRequestPath, $workerResponsePath) `
        -PassThru -Wait -WindowStyle Hidden
    $workerClock.Stop()
    if ($workerProcess.ExitCode -ne 0) { throw "The packaged scientific worker failed ($($workerProcess.ExitCode))." }
    $workerResult = Get-Content -LiteralPath $workerResponsePath -Raw | ConvertFrom-Json
    $workerExpected = Get-Content -LiteralPath $workerExpectedPath -Raw | ConvertFrom-Json
    if ($workerResult.status -ne "COMPLETED" -or $workerResult.result_digest -ne $workerExpected.result_digest) {
        throw "The packaged scientific worker did not reproduce the direct analysis result."
    }
    $benchmarks.scientific_worker = @{
        method_id = $workerResult.method_id
        status = $workerResult.status
        result_digest = $workerResult.result_digest
        result_digest_matches_direct = $true
        elapsed_ms = [Math]::Round($workerClock.Elapsed.TotalMilliseconds, 2)
    }

    $realWorkerResults = [ordered]@{}
    foreach ($label in @("mendeley-trend", "movesmart-reliability", "movesmart-signal")) {
        $requestPath = Join-Path $realDataRoot "tmp\$label-request.json"
        $responsePath = Join-Path $realDataRoot "tmp\$label-response.json"
        $expectedPath = Join-Path $realDataRoot "tmp\$label-expected.json"
        $workerClock = [System.Diagnostics.Stopwatch]::StartNew()
        $realWorker = Start-Process -FilePath $installedExe `
            -ArgumentList @("--worker", $requestPath, $responsePath) `
            -PassThru -Wait -WindowStyle Hidden
        $workerClock.Stop()
        if ($realWorker.ExitCode -ne 0) { throw "The packaged $label worker failed ($($realWorker.ExitCode))." }
        $result = Get-Content -LiteralPath $responsePath -Raw | ConvertFrom-Json
        $expected = Get-Content -LiteralPath $expectedPath -Raw | ConvertFrom-Json
        if ($result.status -ne "COMPLETED" -or $result.method_id -ne $expected.method_id -or
            $result.result_digest -ne $expected.result_digest) {
            throw "The packaged $label worker did not reproduce the direct scientific result."
        }
        $realWorkerResults[$label] = @{
            method_id = $result.method_id
            result_digest = $result.result_digest
            result_digest_matches_direct = $true
            elapsed_ms = [Math]::Round($workerClock.Elapsed.TotalMilliseconds, 2)
        }
    }
    $benchmarks.real_scientific_workers = $realWorkerResults
    # RES-619: the installed engine must produce the corrected, versioned values (R aov / lme4 references).
    $reliability = Get-Content -LiteralPath (Join-Path $realDataRoot "tmp\movesmart-reliability-response.json") -Raw | ConvertFrom-Json
    $trend = Get-Content -LiteralPath (Join-Path $realDataRoot "tmp\mendeley-trend-response.json") -Raw | ConvertFrom-Json
    if ($reliability.method_version -ne "1.1.0" -or $reliability.method_status.state -ne "CURRENT" -or
        [Math]::Abs([double]$reliability.result.icc_3_1 - 0.888726587162) -gt 1e-9 -or
        [Math]::Abs([double]$reliability.result.icc_3_1_ci_low - 0.745195377614) -gt 1e-9 -or
        [Math]::Abs([double]$reliability.result.typical_error - 75.782605988) -gt 1e-6) {
        throw "The packaged reliability worker did not reproduce the RES-619 ICC(3,1) reference."
    }
    if ($trend.method_version -ne "1.1.0" -or $trend.diagnostics.residual_qq_type -ne "CONDITIONAL_PEARSON") {
        throw "The packaged MixedLM worker did not record the RES-619 residual definition."
    }
    $benchmarks.res619_scientific_values = @{
        reliability_method_version = $reliability.method_version
        icc_3_1 = $reliability.result.icc_3_1
        icc_3_1_ci = @($reliability.result.icc_3_1_ci_low, $reliability.result.icc_3_1_ci_high)
        typical_error_n = $reliability.result.typical_error
        minimal_detectable_change_95_n = $reliability.result.minimal_detectable_change_95
        trend_method_version = $trend.method_version
        trend_slope_cm_per_occasion = $trend.result.coefficients.occasion_slope.estimate
        trend_residual_qq_type = $trend.diagnostics.residual_qq_type
    }

    $realQualificationRequestPath = Join-Path $realDataRoot "tmp\real-qualification-request.json"
    $realQualificationResponsePath = Join-Path $realDataRoot "tmp\real-qualification-response.json"
    $realQualificationProcess = Start-Process -FilePath $installedExe `
        -ArgumentList @("--worker", $realQualificationRequestPath, $realQualificationResponsePath) `
        -PassThru -Wait -WindowStyle Hidden
    if ($realQualificationProcess.ExitCode -ne 0) {
        throw "The packaged real-data qualification worker failed ($($realQualificationProcess.ExitCode))."
    }
    $realQualifications = Get-Content -LiteralPath $realQualificationResponsePath -Raw | ConvertFrom-Json
    $qualificationStatuses = @{}
    $qualificationSummary = @()
    foreach ($qualification in $realQualifications) {
        $qualificationStatuses[$qualification.id] = $qualification.status
        $summary = @{ id = $qualification.id; status = $qualification.status }
        if ($qualification.status -eq "BLOCKED") { $summary.reason = $qualification.reason }
        $qualificationSummary += $summary
    }
    if ($qualificationStatuses["QUAL-REAL-RELIABILITY"] -ne "QUALIFIED" -or
        $qualificationStatuses["QUAL-REAL-SIGNAL"] -ne "QUALIFIED" -or
        $qualificationStatuses["QUAL-REAL-MIXEDLM"] -notin @("QUALIFIED", "BLOCKED")) {
        throw "The packaged real-data qualification did not pass or report an honest unavailable state."
    }
    $benchmarks.real_data_qualification = $qualificationSummary

    $benchmarks.runs += Invoke-PackagedSmoke $installedExe "installed-reopen" $installedDataRoot

    $figureRequestPath = Join-Path $installedDataRoot "tmp\figure-worker-request.json"
    $figureResponsePath = Join-Path $installedDataRoot "tmp\figure-worker-response.json"
    $figureProcess = Start-Process -FilePath $installedExe `
        -ArgumentList @("--worker", $figureRequestPath, $figureResponsePath) `
        -PassThru -Wait -WindowStyle Hidden
    if ($figureProcess.ExitCode -ne 0) { throw "The packaged Matplotlib export worker failed ($($figureProcess.ExitCode))." }
    $figureResult = Get-Content -LiteralPath $figureResponsePath -Raw | ConvertFrom-Json
    $expectedDigest = (Get-Content -LiteralPath $workerExpectedPath -Raw | ConvertFrom-Json).result_digest
    if ($figureResult.result_digest -ne $expectedDigest) { throw "The packaged figure uses a different scientific result digest." }
    foreach ($extension in @("png", "pdf", "svg")) {
        $export = $figureResult.exports.$extension
        if ($export.bytes -le 0 -or -not (Test-Path -LiteralPath $export.path)) {
            throw "The packaged Matplotlib $extension export is missing or empty."
        }
    }
    if (-not (Select-String -LiteralPath $figureResult.exports.svg.path -Pattern $expectedDigest -Quiet)) {
        throw "The packaged SVG export is missing its result provenance digest."
    }
    $benchmarks.matplotlib_exports = @{
        extensions = @("png", "pdf", "svg")
        result_digest_matches_direct = $true
        provenance_embedded = $true
    }

    if (-not (Test-Path -LiteralPath (Join-Path $installRoot "_internal\scripts\real_mixedlm.R"))) {
        throw "The installer omitted the independent MixedLM reference script."
    }
    $qualificationRequestPath = Join-Path $installedDataRoot "tmp\qualification-worker-request.json"
    $qualificationResponsePath = Join-Path $installedDataRoot "tmp\qualification-worker-response.json"
    $qualificationProcess = Start-Process -FilePath $installedExe `
        -ArgumentList @("--worker", $qualificationRequestPath, $qualificationResponsePath) `
        -PassThru -Wait -WindowStyle Hidden
    if ($qualificationProcess.ExitCode -ne 0) {
        throw "The packaged qualification worker failed ($($qualificationProcess.ExitCode))."
    }
    $qualificationResult = Get-Content -LiteralPath $qualificationResponsePath -Raw | ConvertFrom-Json
    if (@($qualificationResult).Count -ne 0) {
        throw "The packaged qualification worker should report an honest empty state for the synthetic-only test root."
    }
    $benchmarks.qualification_worker = @{ status = "NO_REAL_SNAPSHOTS"; empty_state = $true }

    $database = Join-Path $installedDataRoot "research\research.db"
    if (-not (Test-Path -LiteralPath $database)) { throw "The installed application did not initialize the configured data root." }
    $databaseHashBeforeMaintenance = (Get-FileHash -LiteralPath $database -Algorithm SHA256).Hash
    $databaseSmokePath = Join-Path $installedDataRoot "tmp\packaged-database-smoke.json"
    $databaseClock = [System.Diagnostics.Stopwatch]::StartNew()
    $databaseProcess = Start-Process -FilePath $installedExe `
        -ArgumentList @("--database-smoke", $installedDataRoot, $databaseSmokePath) `
        -PassThru -Wait -WindowStyle Hidden
    $databaseClock.Stop()
    if ($databaseProcess.ExitCode -ne 0) { throw "The packaged SQLite backup/restore rehearsal failed ($($databaseProcess.ExitCode))." }
    $databaseSmoke = Get-Content -LiteralPath $databaseSmokePath -Raw | ConvertFrom-Json
    if (($databaseSmoke.verification.integrity_check -join ",") -ne "ok") {
        throw "The packaged database integrity check failed."
    }
    if ($databaseSmoke.restore.backup.logical_sha256 -ne $databaseSmoke.restore.restored.logical_sha256) {
        throw "The packaged restore rehearsal changed the logical database state."
    }
    if ((Get-FileHash -LiteralPath $database -Algorithm SHA256).Hash -ne $databaseHashBeforeMaintenance) {
        throw "The packaged backup/restore rehearsal changed the operational database."
    }
    $benchmarks.sqlite_recovery = @{
        integrity_check = $databaseSmoke.verification.integrity_check -join ","
        restore_reopened = $true
        logical_hash_preserved = $true
        operational_database_unchanged = $true
        elapsed_ms = [Math]::Round($databaseClock.Elapsed.TotalMilliseconds, 2)
    }
    $benchmarks.runs += Invoke-PackagedSmoke $installedExe "installed-after-restore" $installedDataRoot
    $databaseHashBeforeUninstall = (Get-FileHash -LiteralPath $database -Algorithm SHA256).Hash
    $uninstaller = Join-Path $installRoot "unins000.exe"
    $uninstallProcess = Start-Process -FilePath $uninstaller `
        -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-") `
        -PassThru -Wait -WindowStyle Hidden
    if ($uninstallProcess.ExitCode -ne 0) { throw "Inno Setup uninstall failed ($($uninstallProcess.ExitCode))." }
    if (Test-Path -LiteralPath $installRoot) { throw "Uninstall left application files at the selected install directory." }
    if ((Get-FileHash -LiteralPath $database -Algorithm SHA256).Hash -ne $databaseHashBeforeUninstall) {
        throw "Uninstall changed the private research database."
    }

    $benchmarks.data_root = "disposable isolated test root"
    $benchmarks.database_survived_uninstall = $true
    $benchmarks.bundle_bytes = (Get-ChildItem -LiteralPath (Join-Path $packagingRecord.FullName "dist\DynamisScience") -File -Recurse | Measure-Object Length -Sum).Sum
    $benchmarks.installer_bytes = (Get-Item -LiteralPath $installer).Length
}
finally {
    if (Test-Path -LiteralPath (Join-Path $installRoot "unins000.exe")) {
        $cleanup = Start-Process -FilePath (Join-Path $installRoot "unins000.exe") `
            -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-") `
            -PassThru -Wait -WindowStyle Hidden
    }
    Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    Remove-Item Env:\DYNAMISSCIENCE_DATA_ROOT -ErrorAction SilentlyContinue
    Remove-Item Env:\DYNAMISSCIENCE_SETTINGS_FILE -ErrorAction SilentlyContinue
    Remove-Item Env:\DYNAMISSCIENCE_BROWSER_BASE -ErrorAction SilentlyContinue
    Remove-Item Env:\DYNAMISSCIENCE_SCIENCE_API -ErrorAction SilentlyContinue
    Remove-Item Env:\DYNAMISSCIENCE_SOURCE_ROOT -ErrorAction SilentlyContinue
    Remove-Item Env:\DYNAMISSCIENCE_REAL_TEST_ROOT -ErrorAction SilentlyContinue
    Remove-Item Env:\HTTP_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:\HTTPS_PROXY -ErrorAction SilentlyContinue
    $tempRootPath = [System.IO.Path]::GetFullPath($env:TEMP).TrimEnd([char]'\')
    $testRootPath = [System.IO.Path]::GetFullPath($testRoot).TrimEnd([char]'\')
    $testRootName = Split-Path -Leaf $testRootPath
    $expectedPrefix = $tempRootPath + [System.IO.Path]::DirectorySeparatorChar + 'dynamis-g4-installer-'
    if (-not $testRootPath.StartsWith($expectedPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or
        $testRootName -notmatch '^dynamis-g4-installer-[0-9a-f]{32}$') {
        throw "Refusing to remove an unexpected installer test directory."
    }
    Remove-Item -LiteralPath $testRootPath -Recurse -Force
}
$benchmarks.temporary_test_root_removed = -not (Test-Path -LiteralPath $testRootPath)
if (-not $benchmarks.temporary_test_root_removed) { throw "The disposable installer test data was not removed." }
$outputPath = Join-Path $repoRoot "docs\desktop\evidence\g4-packaging-benchmarks.json"
$benchmarks | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $outputPath -Encoding utf8
Get-Content -LiteralPath $outputPath -Raw
