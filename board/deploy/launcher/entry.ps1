param([ValidateSet('start','status','check','stop','cold','open','diagnose')][string]$Action='start',[switch]$NoBrowser)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$runtimePython=Join-Path $projectRoot 'experiments/cnn_stereo_20261018/.venv/Scripts/python.exe'
if(-not (Test-Path -LiteralPath $runtimePython)){throw '请先运行项目根目录 setup.cmd；新电脑需自行建立虚拟环境。'}
$guard=New-Object Threading.Mutex($false,'Local\Shenmu_Startup_V1')
$owned=$false
try {
    try {$owned=$guard.WaitOne(0)} catch [Threading.AbandonedMutexException] {$owned=$true}
    if(-not $owned){throw '另一个启动或停止操作尚未结束，请查看它的进度。'}
    & $runtimePython -X utf8 (Join-Path $PSScriptRoot 'startup.py') $Action
    if($LASTEXITCODE -ne 0){throw '本次操作未完成，请查看上方提示和 launcher/logs。'}
    if(($Action -in @('start','cold','open')) -and -not $NoBrowser){
        # Opening the requested workbench is an intentional visible user interface.
        Start-Process -FilePath 'http://127.0.0.1:8849/'
    }
} finally {
    if($owned){$guard.ReleaseMutex()};$guard.Dispose()
}
