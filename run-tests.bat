@echo off
cd /d "%~dp0"
echo Asking Kaki 27 test questions (hawker and employee). Takes about 2 minutes...
".venv\Scripts\python.exe" run_tests.py
if errorlevel 1 (
  echo Something went wrong. Send Claude a screenshot of this window.
  pause
  exit /b 1
)
notepad test_results.txt
