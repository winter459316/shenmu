param([switch]$NoBrowser)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$selectedRoot=Join-Path $projectRoot 'candidates/usb_fast_infer2'
$expectedHost=[IO.Path]::GetFullPath((Join-Path $selectedRoot 'host.py'))
$selectedPython=[IO.Path]::GetFullPath((Join-Path $projectRoot 'experiments/cnn_stereo_20261018/.venv/Scripts/python.exe'))
$fixedUrl='http://127.0.0.1:8849/'
$launcherLog=Join-Path $PSScriptRoot 'web_launcher.log'
$entryMutex=New-Object Threading.Mutex($false,'Local\ZU4EV_Selected_Web_8849')
$ownsMutex=$false

function Get-SelectedListener {
    $listeners=@(Get-NetTCPConnection -LocalPort 8849 -State Listen -ErrorAction SilentlyContinue)
    if($listeners.Count -eq 0){return $null}
    $listenerPids=@($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    if($listenerPids.Count -ne 1){throw '8849 端口存在多个服务，请检查后再打开。'}
    $listenerProcess=Get-CimInstance Win32_Process -Filter ('ProcessId='+$listenerPids[0])
    if(-not $listenerProcess -or $listenerProcess.CommandLine -notmatch [regex]::Escape($expectedHost)){
        throw '8849 端口被其他程序占用；现有程序未被停止。'
    }
    return $listenerProcess
}

try {
    try {$ownsMutex=$entryMutex.WaitOne(30000)}
    catch [Threading.AbandonedMutexException] {$ownsMutex=$true}
    if(-not $ownsMutex){throw '另一个网页入口仍在启动，请稍后再试。'}
    $listenerProcess=Get-SelectedListener
    $started=$false
    if(-not $listenerProcess){
        # Validate the selected release before starting it; never deploy board
        # firmware or start a historical candidate from this desktop entry.
        & $selectedPython -X utf8 (Join-Path $PSScriptRoot 'check_current.py') --offline 2>&1 |
            Out-File -LiteralPath $launcherLog -Encoding utf8
        if($LASTEXITCODE -ne 0){throw '稳定版文件校验未通过，详情见 handoff/web_launcher.log。'}
        & (Join-Path $selectedRoot 'start.ps1')
        $started=$true
    }
    $deadline=[DateTime]::UtcNow.AddSeconds(25)
    do {
        $listenerProcess=Get-SelectedListener
        if($listenerProcess){
            try {
                $state=Invoke-RestMethod -Uri ($fixedUrl+'api/status') -TimeoutSec 2 -UseBasicParsing
                if($state.PSObject.Properties.Name -contains 'busy'){break}
            } catch {$state=$null}
        }
        if([DateTime]::UtcNow -ge $deadline){throw '网页服务启动超时，详情见稳定版 host_stderr.log。'}
        Start-Sleep -Milliseconds 200
    } while($true)
    $receipt=[pscustomobject]@{
        url=$fixedUrl
        pid=$listenerProcess.ProcessId
        started=$started
        checked_at=(Get-Date).ToString('o')
    }
    $receipt | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'web_entry_last.json') -Encoding utf8
    if(-not $NoBrowser){Start-Process -FilePath $fixedUrl}
    $receipt | ConvertTo-Json -Compress
} catch {
    $problem=$_.Exception.Message
    Add-Content -LiteralPath $launcherLog -Value ((Get-Date).ToString('o')+' '+$problem) -Encoding utf8
    if(-not $NoBrowser){
        Add-Type -AssemblyName System.Windows.Forms
        [void][Windows.Forms.MessageBox]::Show($problem,'内窥镜三维工作台')
    }
    throw
} finally {
    if($ownsMutex){$entryMutex.ReleaseMutex()}
    $entryMutex.Dispose()
}
