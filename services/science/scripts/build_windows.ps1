param([string]$AppVersion = "0.1.0")

$ErrorActionPreference = "Stop"

# Windows PowerShell 5.1 turns every line a native command writes to stderr into a terminating
# NativeCommandError under $ErrorActionPreference = "Stop" once the caller merges streams (2>&1, a CI
# log, a hidden launcher). uv and PyInstaller write warnings to stderr, so the build used to stop silently
# between PyInstaller and Inno Setup. Native commands run here with stderr kept as text and only the exit
# code decides success; a failure prints the tail of the output, throws, and the script exits non-zero.
function Invoke-Native {
    param([Parameter(Mandatory)][string]$What, [Parameter(Mandatory)][scriptblock]$Command)
    $saved = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { $lines = @(& $Command 2>&1 | ForEach-Object { "$_" }) }
    finally { $ErrorActionPreference = $saved }
    if ($LASTEXITCODE -ne 0) {
        $lines | Select-Object -Last 20 | ForEach-Object { [Console]::Error.WriteLine($_) }
        throw "$What failed (exit code $LASTEXITCODE)."
    }
    return $lines
}

$serviceRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$buildName = "res604-" + (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
$buildRoot = Join-Path (Join-Path $serviceRoot "build") $buildName
$fixtureRoot = Join-Path $buildRoot "fixture-data"
$thirdPartyNotices = Join-Path $buildRoot "THIRD_PARTY_NOTICES.txt"
$distRoot = Join-Path $buildRoot "dist"
$bundleRoot = Join-Path $distRoot "DynamisScience"
$workRoot = Join-Path $buildRoot "work"
$installerRoot = Join-Path $distRoot "installer"
$innoCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
$isccPath = if ($innoCommand) { $innoCommand.Source } else { $null }
if (-not $isccPath) {
    $candidate = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
    if (Test-Path -LiteralPath $candidate) { $isccPath = $candidate }
}
if (-not $isccPath) { throw "Inno Setup compiler ISCC.exe was not found." }

New-Item -ItemType Directory -Path $fixtureRoot, $workRoot, $installerRoot -Force | Out-Null
$env:DYNAMISSCIENCE_FIXTURE_DIR = $fixtureRoot
$env:DYNAMISSCIENCE_THIRD_PARTY_NOTICES = $thirdPartyNotices
Push-Location $serviceRoot
try {
    Invoke-Native "Generating the bundled synthetic fixture" { uv run python -m dynamis_science.generate } | Out-Host
    if (-not (Test-Path -LiteralPath (Join-Path $fixtureRoot "artifacts\dataset_snapshot.json"))) {
        throw "The generated synthetic snapshot manifest is missing."
    }

    Invoke-Native "Collecting third-party license notices" {
        uv run python scripts\build_third_party_notices.py --output $thirdPartyNotices } | Out-Host

    $originalPath = $env:PATH
    $uvDirectory = Split-Path -Parent (Get-Command uv.exe).Source
    $venvScripts = Join-Path $serviceRoot ".venv\Scripts"
    $cleanBuildPath = @(
        $uvDirectory,
        $venvScripts,
        (Join-Path $env:WINDIR "System32"),
        $env:WINDIR,
        (Join-Path $env:WINDIR "System32\Wbem"),
        (Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0")
    ) -join ";"
    try {
        $env:PATH = $cleanBuildPath
        Invoke-Native "PyInstaller (onedir application)" {
            uv run python -m PyInstaller packaging\DynamisScience.spec --noconfirm --clean --log-level WARN --distpath $distRoot --workpath $workRoot } | Out-Host
    }
    finally {
        $env:PATH = $originalPath
    }
    if (-not (Test-Path -LiteralPath (Join-Path $bundleRoot "DynamisScience.exe"))) {
        throw "The PyInstaller executable was not produced."
    }

    $innoArgs = @(
        "/DAppVersion=$AppVersion",
        "/DDistDir=$bundleRoot",
        "/DOutputDir=$installerRoot",
        (Join-Path $serviceRoot "packaging\DynamisScience.iss")
    )
    Invoke-Native "Inno Setup (per-user installer)" { & $isccPath /Qp @innoArgs } | Out-Host

    $bundleBytes = (Get-ChildItem -LiteralPath $bundleRoot -File -Recurse | Measure-Object -Property Length -Sum).Sum
    $installerPath = Join-Path $installerRoot "DynamisScience-Setup-x64.exe"
    if (-not (Test-Path -LiteralPath $installerPath)) { throw "Inno Setup reported success but $installerPath was not produced." }
    $installer = Get-Item -LiteralPath $installerPath
    $sourceDiffPath = Join-Path $buildRoot ".source-diff.tmp"
    Push-Location $repoRoot
    try {
        $sourceCommit = (Invoke-Native "Recording the source Git commit" { git rev-parse HEAD }) -join ""
        $sourceStatus = @(Invoke-Native "Recording the source working-tree state" { git status --porcelain --untracked-files=all })
        Invoke-Native "Fingerprinting the source diff" { git diff --binary HEAD "--output=$sourceDiffPath" } | Out-Null
        $sourceDiffSha256 = (Get-FileHash -LiteralPath $sourceDiffPath -Algorithm SHA256).Hash
    }
    finally {
        Remove-Item -LiteralPath $sourceDiffPath -Force -ErrorAction SilentlyContinue
        Pop-Location
    }
    $report = [ordered]@{
        source_commit = $sourceCommit
        source_status = $sourceStatus
        source_diff_sha256 = $sourceDiffSha256
        app_version = $AppVersion
        python_version = (Invoke-Native "Python version" { uv run python --version }) -join " "
        pyinstaller_version = (Invoke-Native "PyInstaller version" { uv run python -m PyInstaller --version }) -join " "
        inno_setup = $isccPath
        fixture = "DS-SYNTH-001 generated in an isolated build directory"
        bundle_bytes = [long]$bundleBytes
        installer_bytes = [long]$installer.Length
        executable = (Join-Path $bundleRoot "DynamisScience.exe")
        installer = $installer.FullName
    }
    $reportPath = Join-Path $buildRoot "packaging-measurements.json"
    $report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $reportPath -Encoding utf8
    Write-Output (Get-Content -LiteralPath $reportPath -Raw)
}
finally {
    Pop-Location
    Remove-Item Env:\DYNAMISSCIENCE_FIXTURE_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:\DYNAMISSCIENCE_THIRD_PARTY_NOTICES -ErrorAction SilentlyContinue
}
