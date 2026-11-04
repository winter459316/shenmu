param(
 [string]$VivadoRoot='',
 [string]$WorkRoot='',
 [switch]$Resume,
 [string]$IPCache=''
)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
if(-not $WorkRoot){$WorkRoot=Join-Path $projectRoot 'build/output'}
if(-not $VivadoRoot){$VivadoRoot=$env:XILINX_VIVADO}
if(-not $VivadoRoot){$tool=Get-Command vivado.bat -ErrorAction SilentlyContinue; if($tool){$VivadoRoot=Split-Path (Split-Path $tool.Source -Parent) -Parent}}
if(-not $VivadoRoot){throw 'Set -VivadoRoot to the Vivado 2026.1 installation directory.'}
$vivado=Join-Path $VivadoRoot 'bin/vivado.bat'
if(-not(Test-Path -LiteralPath $vivado)){throw 'Vivado 2026.1 was not found.'}
$completed=@()
foreach($profile in @('pl1','pl2','pl3')){
 $work=Join-Path $WorkRoot $profile
 $existing=Test-Path -LiteralPath (Join-Path $work ('project/shenmu_'+$profile+'.xpr'))
 if($existing -and -not $Resume){throw 'Existing project: use -Resume or a fresh WorkRoot.'}
 & (Join-Path $PSScriptRoot 'build.ps1') -Profile $profile -VivadoRoot $VivadoRoot -WorkRoot $WorkRoot -Step bit -Resume:($Resume -and $existing) -IPCache $IPCache
 $completed+=@{profile=$profile;work=$work;physical_review_passed=$true;board_tested=$false}
 $completed | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $WorkRoot 'build_summary.json') -Encoding utf8
}
Write-Host 'Three physical builds passed. Board qualification is a separate step; no board was programmed.'
