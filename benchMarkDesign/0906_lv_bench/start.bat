@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0..\..\backend\.venv\Scripts\python.exe"
if exist "%PYTHON_EXE%" goto run
set "PYTHON_EXE=%~dp0..\..\AIMonitor\backend\.venv\Scripts\python.exe"
if exist "%PYTHON_EXE%" goto run

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Run setup first; see README.md.
  pause
  exit /b 1
)
set "PYTHON_EXE=python"

:run
"%PYTHON_EXE%" run.py

