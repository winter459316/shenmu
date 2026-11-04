param([ValidateSet('start','status','check','stop','cold','open','diagnose')][string]$Action='start',[switch]$NoBrowser)
$ErrorActionPreference='Stop'
$repoRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$entry=Join-Path $repoRoot '.runtime/zu4ev_stereo/launcher/entry.ps1'
if(-not(Test-Path -LiteralPath $entry)){throw 'Run setup.cmd first; see README.md for runtime setup.'}
try { & $entry -Action $Action -NoBrowser:$NoBrowser }
catch {
    $problem=$_.Exception.Message
    $log=Join-Path $repoRoot '.runtime/zu4ev_stereo/launcher/logs/entry_error.log'
    $folder=Split-Path -Parent $log
    if(Test-Path -LiteralPath $folder){Add-Content -LiteralPath $log -Value $problem -Encoding UTF8}
    if(-not $NoBrowser){
        Add-Type -AssemblyName System.Windows.Forms
        [void][Windows.Forms.MessageBox]::Show(($problem+"`n"+$log),'Shenmu 2026.1')
    }
    throw
}
