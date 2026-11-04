param([switch]$NoBrowser,[switch]$Rollback)
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$python=Join-Path $projectRoot 'experiments/cnn_stereo_20261018/.venv/Scripts/python.exe'
$taskArgs=@('-X','utf8',(Join-Path $PSScriptRoot 'select_mode.py'))
if($Rollback){$taskArgs+='--rollback'}
$entryMutex=New-Object Threading.Mutex($false,'Local\ZU4EV_PL3_Usable_Mode')
$ownsMutex=$false
try {
    try {$ownsMutex=$entryMutex.WaitOne(90000)}
    catch [Threading.AbandonedMutexException] {$ownsMutex=$true}
    if(-not $ownsMutex){throw 'Another PL3 runtime selection is still in progress.'}
    & $python @taskArgs 2>&1 | Tee-Object -FilePath (Join-Path $PSScriptRoot 'selection_last.log')
    if($LASTEXITCODE -ne 0){throw 'Runtime selection failed; inspect selection_last.log. Do not force FPGA reconfiguration.'}
    if(-not $Rollback){
        & $python -X utf8 (Join-Path $projectRoot 'candidates/usb_fast_infer2/video_deploy.py')
        if($LASTEXITCODE -ne 0){throw 'HDMI display extension did not become ready; inspect its installation log.'}
    }
    & (Join-Path $projectRoot 'handoff/open_web.ps1') -NoBrowser:$NoBrowser
} catch {
    if(-not $NoBrowser){
        Add-Type -AssemblyName System.Windows.Forms
        [void][Windows.Forms.MessageBox]::Show($_.Exception.Message,'PL + PL runtime')
    }
    throw
} finally {
    if($ownsMutex){$entryMutex.ReleaseMutex()}
    $entryMutex.Dispose()
}
