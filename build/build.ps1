param(
 [Parameter(Mandatory=$true)][ValidateSet('pl1','pl2','pl3')][string]$Profile,
 [string]$VivadoRoot='',
 [ValidateSet('project','synth','bit')][string]$Step='project',
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
if(-not(Test-Path -LiteralPath $vivado)){throw 'VivadoRoot must point to the 2026.1 Vivado directory.'}
$work=Join-Path $WorkRoot $Profile
if((Test-Path -LiteralPath (Join-Path $work 'project')) -and -not $Resume){throw 'Build directory already contains a project. Use -Resume or choose a new WorkRoot.'}
New-Item -ItemType Directory -Force -Path $work | Out-Null
$script=Join-Path $PSScriptRoot 'tools/migrate.tcl'
$runStep=$Step
if($Resume){
 if(-not(Test-Path -LiteralPath (Join-Path $work ('project/shenmu_'+$Profile+'.xpr')))){throw 'No matching project to resume.'}
 $script=Join-Path $PSScriptRoot 'tools/resume_build.tcl'
 if($Step -eq 'project'){$runStep='audit'}
}
$shenmuPreviousLocalData=[Environment]::GetEnvironmentVariable('XILINX_LOCAL_USER_DATA','Process')
try {
 # Disable only Tcl catalog caching for this build process and its children.
 # The design's OOC synthesis cache is separate and remains enabled.
 $env:XILINX_LOCAL_USER_DATA='NO'
 & $vivado -mode batch -nojournal -nolog -source $script -tclargs $projectRoot $Profile $work $runStep $IPCache *> (Join-Path $work 'migration.log')
 $shenmuVivadoExit=$LASTEXITCODE
} finally {
 [Environment]::SetEnvironmentVariable('XILINX_LOCAL_USER_DATA',$shenmuPreviousLocalData,'Process')
}
if($shenmuVivadoExit -ne 0){throw ('Vivado migration/build failed. See '+(Join-Path $work 'migration.log'))}
if($Resume){$marker='SHENMU_2026_ABI_PASS '+$Profile}else{$marker='SHENMU_2026_PROJECT_PASS '+$Profile}
if(-not(Select-String -LiteralPath (Join-Path $work 'migration.log') -SimpleMatch $marker -Quiet)){throw 'Success marker missing.'}
if($Step -eq 'synth'){$stageMarker='SHENMU_2026_SYNTH_PASS '+$Profile}
elseif($Step -eq 'bit'){$stageMarker='SHENMU_2026_ROUTE_TIMING_PASS '+$Profile}
else{$stageMarker=$marker}
if(-not(Select-String -LiteralPath (Join-Path $work 'migration.log') -SimpleMatch $stageMarker -Quiet)){throw 'Requested build stage did not pass.'}
if($Step -eq 'bit'){
 foreach($phase in @('review_implementation','export_bit')){
  $phaseLog=Join-Path $work ($phase+'.log')
  $prior=[Environment]::GetEnvironmentVariable('XILINX_LOCAL_USER_DATA','Process')
  try {
   $env:XILINX_LOCAL_USER_DATA='NO'
   & $vivado -mode batch -nojournal -nolog -source (Join-Path $PSScriptRoot ('tools/'+$phase+'.tcl')) -tclargs $work $Profile *> $phaseLog
   $phaseExit=$LASTEXITCODE
  } finally {[Environment]::SetEnvironmentVariable('XILINX_LOCAL_USER_DATA',$prior,'Process')}
  if($phase -eq 'export_bit'){$success='SHENMU_2026_BIT_EXPORT_PASS '+$Profile}else{$success='SHENMU_2026_IMPLEMENTATION_REVIEW_PASS '+$Profile}
  if($phaseExit -ne 0 -or -not(Select-String -LiteralPath $phaseLog -SimpleMatch $success -Quiet)){throw ('Hardware phase failed: '+$phase)}
 }
 $bit=Join-Path $work 'artifacts/system_wrapper.bit'
 @{profile=$Profile;vivado='2026.1';physical_review_passed=$true;bit_sha256=(Get-FileHash -LiteralPath $bit -Algorithm SHA256).Hash.ToLower();checkpoint_sha256=(Get-FileHash -LiteralPath (Join-Path $work 'artifacts/reviewed_routed.dcp') -Algorithm SHA256).Hash.ToLower();board_tested=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $work 'artifacts/build_receipt.json') -Encoding utf8
 Write-Host ('SHENMU_2026_BIT_TIMING_PASS '+$Profile)
}
Write-Host ('Project prepared in '+$work+'. No board programming has been performed.')
