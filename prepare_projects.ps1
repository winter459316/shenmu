param(
 [string]$VivadoRoot='',
 [string]$WorkRoot='',
 [switch]$Resume
)
& (Join-Path $PSScriptRoot 'build/prepare_projects.ps1') @PSBoundParameters
