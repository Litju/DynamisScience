$ErrorActionPreference = "Stop"
$serviceRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
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

$testRoot = Join-Path $env:TEMP ("dynamis-g4-installer-" + [guid]::NewGuid().ToString("N"))
$onedirDataRoot = Join-Path $testRoot "onedir-data"
$installedDataRoot = Join-Path $testRoot "installed-data"
$installRoot = Join-Path $testRoot "installed-app"
$benchmarks = [ordered]@{ platform = [System.Environment]::OSVersion.VersionString; runs = @(); network_listeners = @() }
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$env:QT_QPA_PLATFORM = "windows"
$env:DYNAMISSCIENCE_BROWSER_BASE = ""
$env:DYNAMISSCIENCE_SCIENCE_API = ""
$env:HTTP_PROXY = "http://127.0.0.1:9"
$env:HTTPS_PROXY = "http://127.0.0.1:9"

function Invoke-PackagedSmoke([string]$Executable, [string]$Label, [string]$DataRoot) {
    $env:DYNAMISSCIENCE_DATA_ROOT = $DataRoot
    $env:DYNAMISSCIENCE_SETTINGS_FILE = Join-Path $testRoot ($Label + "-settings.json")
    $ready = Join-Path $testRoot ($Label + "-ready.txt")
    $clock = [System.Diagnostics.Stopwatch]::StartNew()
    $process = Start-Process -FilePath $Executable `
        -ArgumentList @("--data-root", $DataRoot, "--benchmark-ready-file", $ready, "--benchmark-exit-after-ready") `
        -PassThru
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
    $benchmarks.runs += Invoke-PackagedSmoke $installedExe "installed" $installedDataRoot

    $workerRequestPath = Join-Path $installedDataRoot "tmp\packaged-worker-request.json"
    $workerResponsePath = Join-Path $installedDataRoot "tmp\packaged-worker-response.json"
    $workerExpectedPath = Join-Path $installedDataRoot "tmp\packaged-worker-expected.json"
    $seedCode = @'
import json, os
from pathlib import Path
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
        result_digest_matches_direct = $true
        elapsed_ms = [Math]::Round($workerClock.Elapsed.TotalMilliseconds, 2)
    }

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

    $benchmarks.data_root = $installedDataRoot
    $benchmarks.database_survived_uninstall = $true
    $benchmarks.bundle_bytes = (Get-ChildItem -LiteralPath (Join-Path $packagingRecord.FullName "dist\DynamisScience") -File -Recurse | Measure-Object Length -Sum).Sum
    $benchmarks.installer_bytes = (Get-Item -LiteralPath $installer).Length
    $outputPath = Join-Path $repoRoot "docs\desktop\evidence\g4-packaging-benchmarks.json"
    $benchmarks | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $outputPath -Encoding utf8
    Get-Content -LiteralPath $outputPath -Raw
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
    Remove-Item Env:\HTTP_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:\HTTPS_PROXY -ErrorAction SilentlyContinue
}
