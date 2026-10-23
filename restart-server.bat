@echo off
cd /d "%~dp0"
echo Restarting only the Kaki server. Your tunnel address stays the same.
echo First close the old "Kaki server" window if it is still open.
start "Kaki server - keep open" cmd /k ".venv\Scripts\python.exe -m uvicorn app:app --port 8000"
timeout /t 3 >nul
