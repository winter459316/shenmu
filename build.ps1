param(
 [Parameter(Mandatory=$true)][ValidateSet('pl1','pl2','pl3')][string]$Profile,
 [string]$VivadoRoot='',
 [ValidateSet('project','synth','bit')][string]$Step='project',
 [string]$WorkRoot='',
 [switch]$Resume,
 [string]$IPCache=''
)
& (Join-Path $PSScriptRoot 'build/build.ps1') @PSBoundParameters
