@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0board\deploy\control.ps1" -Action status
pause
