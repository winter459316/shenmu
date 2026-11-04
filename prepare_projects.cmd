@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0prepare_projects.ps1" %*
pause
