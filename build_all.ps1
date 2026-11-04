param(
 [string]$VivadoRoot='',
 [string]$WorkRoot='',
 [switch]$Resume,
 [string]$IPCache=''
)
& (Join-Path $PSScriptRoot 'build/build_all.ps1') @PSBoundParameters
