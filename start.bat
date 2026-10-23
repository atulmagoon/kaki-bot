@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
call :findcf
if not defined CF (
  echo The Cloudflare tunnel is not installed yet. Run setup.bat again.
  pause
  exit /b 1
)
start "Kaki server - keep open" cmd /k ".venv\Scripts\python.exe -m uvicorn app:app --port 8000"
start "Kaki tunnel - keep open" cmd /k ""%CF%" tunnel --url http://localhost:8000"
echo.
echo ============================================
echo   Two windows opened. Keep both open.
echo   In the "Kaki tunnel" window, find the line
echo   with https://....trycloudflare.com
echo   That address + /whatsapp goes into Twilio's
echo   Sandbox settings, "When a message comes in".
echo ============================================
pause
exit /b 0

:findcf
set "CF="
for /f "delims=" %%i in ('where cloudflared 2^>nul') do set "CF=%%i"
if not defined CF if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\cloudflared.exe" set "CF=%LOCALAPPDATA%\Microsoft\WinGet\Links\cloudflared.exe"
if not defined CF if exist "%ProgramFiles(x86)%\cloudflared\cloudflared.exe" set "CF=%ProgramFiles(x86)%\cloudflared\cloudflared.exe"
if not defined CF if exist "%ProgramFiles%\cloudflared\cloudflared.exe" set "CF=%ProgramFiles%\cloudflared\cloudflared.exe"
exit /b 0
