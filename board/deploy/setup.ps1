param([string]$PythonExe='', [string]$PrivateRoot='')
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
& (Join-Path $root 'setup.ps1') @PSBoundParameters
