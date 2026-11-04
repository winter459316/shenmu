$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$files=Get-ChildItem -LiteralPath $root -Filter *.ps1 -Recurse | Where-Object { $_.FullName -notmatch '\\.runtime\\|\\.venv\\' }
$failures=0
foreach($file in $files){
 $parseErrors=$null
 $tokens=$null
 [void][System.Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$parseErrors)
 if($parseErrors){$failures++;Write-Output $file.FullName;$parseErrors | ForEach-Object {Write-Output $_.Message}}
}
if($failures){throw "$failures PowerShell scripts failed parsing"}
Write-Output "POWERSHELL_PARSE_PASS files=$($files.Count) version=$($PSVersionTable.PSVersion)"
