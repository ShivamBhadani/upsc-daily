@echo off
rem Daily publish for Task Scheduler: collect the news, set the paper, build the
rem site, push it. Logs land in logs\. Exits non-zero when the day got no paper.

setlocal
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" "tools\daily_run.py" %*
exit /b %ERRORLEVEL%
