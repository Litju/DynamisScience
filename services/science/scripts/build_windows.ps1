param([string]$AppVersion = "0.1.0")

$ErrorActionPreference = "Stop"
$serviceRoot = Split-Path -Parent $PSScriptRoot
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
    uv run python -m dynamis_science.generate
    if ($LASTEXITCODE -ne 0) { throw "Generating the bundled synthetic fixture failed." }
    if (-not (Test-Path -LiteralPath (Join-Path $fixtureRoot "artifacts\dataset_snapshot.json"))) {
        throw "The generated synthetic snapshot manifest is missing."
    }

    uv run python scripts\build_third_party_notices.py --output $thirdPartyNotices
    if ($LASTEXITCODE -ne 0) { throw "Collecting third-party license notices failed." }

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
        uv run python -m PyInstaller packaging\DynamisScience.spec --noconfirm --clean --log-level WARN --distpath $distRoot --workpath $workRoot
    }
    finally {
        $env:PATH = $originalPath
    }
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed to build the onedir application." }
    if (-not (Test-Path -LiteralPath (Join-Path $bundleRoot "DynamisScience.exe"))) {
        throw "The PyInstaller executable was not produced."
    }

    $innoArgs = @(
        "/DAppVersion=$AppVersion",
        "/DDistDir=$bundleRoot",
        "/DOutputDir=$installerRoot",
        (Join-Path $serviceRoot "packaging\DynamisScience.iss")
    )
    & $isccPath /Qp @innoArgs
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed to build the per-user installer." }

    $bundleBytes = (Get-ChildItem -LiteralPath $bundleRoot -File -Recurse | Measure-Object -Property Length -Sum).Sum
    $installer = Get-Item -LiteralPath (Join-Path $installerRoot "DynamisScience-Setup-x64.exe")
    $sourceCommit = (& git -C $repoRoot rev-parse HEAD | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Could not record the source Git commit." }
    $sourceStatus = @(& git -C $repoRoot status --porcelain --untracked-files=all)
    if ($LASTEXITCODE -ne 0) { throw "Could not record the source working-tree state." }
    $sourceDiffPath = Join-Path $buildRoot ".source-diff.tmp"
    try {
        & git -C $repoRoot diff --binary HEAD "--output=$sourceDiffPath"
        if ($LASTEXITCODE -ne 0) { throw "Could not fingerprint the source diff." }
        $sourceDiffSha256 = (Get-FileHash -LiteralPath $sourceDiffPath -Algorithm SHA256).Hash
    }
    finally {
        Remove-Item -LiteralPath $sourceDiffPath -Force -ErrorAction SilentlyContinue
    }
    $report = [ordered]@{
        source_commit = $sourceCommit
        source_status = $sourceStatus
        source_diff_sha256 = $sourceDiffSha256
        app_version = $AppVersion
        python_version = (uv run python --version 2>&1 | Out-String).Trim()
        pyinstaller_version = (uv run python -m PyInstaller --version 2>&1 | Out-String).Trim()
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
