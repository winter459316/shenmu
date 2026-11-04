$ErrorActionPreference = 'Stop'
$experimentRoot = $PSScriptRoot
$experimentPython = Join-Path $experimentRoot '.venv/Scripts/python.exe'
$existingListener = Get-NetTCPConnection -LocalPort 8812 -State Listen -ErrorAction SilentlyContinue
if ($existingListener) { throw 'Port 8812 is already in use; existing process was not changed.' }
$argumentLine = '-X utf8 -m http.server 8812 --bind 127.0.0.1 --directory "' + (Join-Path $experimentRoot 'comparison') + '"'
$experimentProcess = Start-Process -FilePath $experimentPython -ArgumentList $argumentLine -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $experimentRoot 'server_stdout.log') -RedirectStandardError (Join-Path $experimentRoot 'server_stderr.log')
@{pid=$experimentProcess.Id; url='http://127.0.0.1:8812/'; scope='offline model comparison only'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $experimentRoot 'comparison_server.json') -Encoding utf8
Write-Output 'http://127.0.0.1:8812/'
