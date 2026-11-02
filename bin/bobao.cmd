@echo off
rem Runs Bobao from wherever this checkout is (Windows).
set "PYTHONPATH=%~dp0..;%PYTHONPATH%"
set "PYTHONUTF8=1"
where py >nul 2>nul
if %errorlevel%==0 (py -3 -m bobao %*) else (python -m bobao %*)
