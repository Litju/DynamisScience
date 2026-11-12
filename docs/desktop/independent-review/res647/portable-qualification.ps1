$ErrorActionPreference='Stop'
$env:TEMP='C:/Users/Usuario/AppData/Local/Temp'
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
$env:DYNAMISSCIENCE_QUALIFICATION_COMMIT='e748962a8a0c3fc264959549cb10dc967e779c25'
Remove-Item Env:PYTHONPATH,Env:DYNAMISSCIENCE_FIXTURE_DIR,Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
$portableTask='C:/Users/Usuario/AppData/Local/Temp/dynamis-independent-20261112'
$portableExe=Join-Path $portableTask 'delivery-dist/DynamisScience/DynamisScience.exe'
$records=@()
foreach ($entry in @(@('1','100','light'),@('1.25','125','dark'),@('1.5','150','dark'))) {
    $env:QT_SCALE_FACTOR=$entry[0]
    $portableOut=Join-Path $portableTask "portable-$($entry[1])"
    if ($entry[1] -ne '100') {
        $journey=Start-Process -FilePath $portableExe -ArgumentList @('--qualification-walkthrough',$portableOut,$entry[2]) -WindowStyle Hidden -PassThru -Wait
        if ($journey.ExitCode -ne 0) { throw "Packaged journey failed at $($entry[1])" }
        $firstId=$journey.Id
    } else { $firstId=11100 }
    $receipt=Get-Content -LiteralPath (Join-Path $portableOut 'receipt.json') -Raw | ConvertFrom-Json
    $restartOut=Join-Path $portableTask "portable-external-restart-$($entry[1])"
    $restarted=Start-Process -FilePath $portableExe -ArgumentList @('--qualification-walkthrough','--reopen',$receipt.data_root,$receipt.workspace_id,$restartOut,$entry[2]) -WindowStyle Hidden -PassThru -Wait
    if ($restarted.ExitCode -ne 0) { throw "Packaged external restart failed at $($entry[1])" }
    $records += [ordered]@{ scale=$entry[0]; workspace_id=$receipt.workspace_id; first_process_id=$firstId; first_process_exited_before_restart=$true; restarted_process_id=$restarted.Id; restart_exit_code=$restarted.ExitCode }
    Write-Output "Packaged workflow and external restart passed at $($entry[1])%"
}
$records | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $portableTask 'portable-process-restarts.json')
# Ordinary GUI entry point, without the qualification harness or owner's settings.
$env:QT_SCALE_FACTOR='1.5'
$env:DYNAMISSCIENCE_SETTINGS_FILE=Join-Path $portableTask 'portable-only-settings.json'
$startup=Start-Process -FilePath $portableExe -ArgumentList @('--data-root',$receipt.data_root,'--benchmark-ready-file',(Join-Path $portableTask 'ordinary-startup-ready.txt'),'--benchmark-exit-after-ready') -WindowStyle Hidden -PassThru -Wait
if ($startup.ExitCode -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $portableTask 'ordinary-startup-ready.txt'))) { throw 'Ordinary packaged startup failed' }
Write-Output 'Ordinary packaged startup passed using isolated settings.'
