@echo off
rem «Вектор» — запуск одной командой из проводника или cmd.
rem Двойной клик по start.bat равнозначен: powershell -ExecutionPolicy Bypass -File run.ps1
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
if errorlevel 1 pause
