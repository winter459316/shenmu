$ErrorActionPreference='Stop'
$trialPython=Join-Path $PSScriptRoot '../../experiments/cnn_stereo_20261018/.venv/Scripts/python.exe'
if(Get-NetTCPConnection -LocalPort 8849 -State Listen -ErrorAction SilentlyContinue){throw '8849 is already running; existing service untouched'}
$trialArgs='-X utf8 "'+(Join-Path $PSScriptRoot 'host.py')+'"'
$trialProcess=Start-Process -FilePath $trialPython -ArgumentList $trialArgs -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'host_stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'host_stderr.log')
@{pid=$trialProcess.Id;url='http://127.0.0.1:8849/';iterations=2}|ConvertTo-Json|Set-Content (Join-Path $PSScriptRoot 'host_process.json')
