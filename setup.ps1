param([string]$PythonExe='', [string]$PrivateRoot='')
$ErrorActionPreference='Stop'
$packageRoot=$PSScriptRoot
if(-not $PrivateRoot){
    $PrivateRoot=Join-Path $packageRoot 'private_runtime'
    if(-not(Test-Path -LiteralPath $PrivateRoot)){$PrivateRoot=[IO.Path]::GetFullPath((Join-Path $packageRoot '../private_runtime'))}
}
if(-not $PythonExe){
    $launcher=Get-Command py.exe -ErrorAction SilentlyContinue
    if($launcher){$PythonExe=(& $launcher.Source -3.12 -c 'import sys; print(sys.executable)')}
    else{$PythonExe=(Get-Command python.exe -ErrorAction Stop).Source}
}
& $PythonExe -c 'import sys; assert sys.version_info[:2]==(3,12) and sys.maxsize>2**32, "Use Python 3.12 x64"'
if($LASTEXITCODE -ne 0){throw 'Python 3.12 x64 is required.'}
$prepare=Join-Path $packageRoot 'board/deploy/prepare_runtime.py'
$assets=Join-Path $PrivateRoot 'runtime_assets.zip'
if(Test-Path -LiteralPath (Join-Path $PrivateRoot 'asset_parts.json')){
    $assets=Join-Path $packageRoot '.runtime/cache/runtime_assets.zip'
    & $PythonExe -X utf8 (Join-Path $packageRoot 'board/deploy/assemble_runtime_assets.py') --parts-directory $PrivateRoot --output $assets
    if($LASTEXITCODE -ne 0){throw 'Runtime asset parts could not be verified or assembled.'}
}
& $PythonExe -X utf8 $prepare --assets $assets
if($LASTEXITCODE -ne 0){throw 'Runtime source/asset verification failed.'}
$runtime=Join-Path $packageRoot '.runtime/zu4ev_stereo'
$venv=Join-Path $runtime 'experiments/cnn_stereo_20261018/.venv'
if(-not(Test-Path -LiteralPath $venv)){
    & $PythonExe -m venv $venv
    if($LASTEXITCODE -ne 0){throw 'Cannot create environment.'}
}
$runtimePython=Join-Path $venv 'Scripts/python.exe'
& $runtimePython -m pip install --no-index --find-links (Join-Path $PrivateRoot 'wheels') -r (Join-Path $packageRoot 'board/config/requirements_runtime.txt')
if($LASTEXITCODE -ne 0){throw 'Offline dependency installation failed.'}
& $runtimePython -X utf8 (Join-Path $runtime 'launcher/startup.py') check
if($LASTEXITCODE -ne 0){throw 'Qualified runtime binding check failed.'}
& $runtimePython -X utf8 (Join-Path $packageRoot 'sim/verify_software.py')
if($LASTEXITCODE -ne 0){throw 'Offline software replay failed.'}
Write-Host 'Ready. Set the serial port in .runtime/zu4ev_stereo/launcher/config.json, then use status.cmd.'
