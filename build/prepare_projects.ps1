param(
 [string]$VivadoRoot='',
 [string]$WorkRoot='',
 [switch]$Resume
)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
if(-not $WorkRoot){$WorkRoot=Join-Path $projectRoot 'build/output'}
if(-not $VivadoRoot){$VivadoRoot=$env:XILINX_VIVADO}
if(-not $VivadoRoot){$tool=Get-Command vivado.bat -ErrorAction SilentlyContinue; if($tool){$VivadoRoot=Split-Path (Split-Path $tool.Source -Parent) -Parent}}
if(-not $VivadoRoot){throw 'Set -VivadoRoot to the Vivado 2026.1 installation directory.'}
foreach($profile in @('pl1','pl2','pl3')){
 $existing=Test-Path -LiteralPath (Join-Path $WorkRoot ($profile+'/project/shenmu_'+$profile+'.xpr'))
 & (Join-Path $PSScriptRoot 'build.ps1') -Profile $profile -VivadoRoot $VivadoRoot -WorkRoot $WorkRoot -Step project -Resume:($existing -and $Resume)
}
Write-Host "Projects ready in $WorkRoot. Open each profile/project/shenmu_PROFILE.xpr in Vivado 2026.1. No synthesis, implementation or board programming was requested."
