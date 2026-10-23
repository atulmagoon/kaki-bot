@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo   Kaki setup: installs Python, the tunnel
echo   and the bot's packages. Takes ~5 minutes.
echo ============================================
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo Installing Python 3.12...
  winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
)
where py >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python was installed but Windows has not picked it up yet.
  echo Close this window and double-click setup.bat again.
  pause
  exit /b 1
)

call :findcf
if not defined CF (
  echo Installing the Cloudflare tunnel...
  winget install -e --id Cloudflare.cloudflared --silent --accept-package-agreements --accept-source-agreements
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the bot's Python environment...
  py -3 -m venv .venv
)
echo Installing the bot's packages...
".venv\Scripts\python.exe" -m pip install -q --upgrade pip
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo.
  echo Package install failed. Send Claude a screenshot of this window.
  pause
  exit /b 1
)

if not exist ".env" copy /y "env.example.txt" ".env" >nul
echo.
echo ============================================
echo   Almost done. Notepad will open now.
echo   Paste your Anthropic key, Twilio Account SID
echo   and Twilio Auth Token, then Save and close.
echo   Then double-click start.bat.
echo ============================================
notepad ".env"
pause
exit /b 0

:findcf
set "CF="
for /f "delims=" %%i in ('where cloudflared 2^>nul') do set "CF=%%i"
if not defined CF if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\cloudflared.exe" set "CF=%LOCALAPPDATA%\Microsoft\WinGet\Links\cloudflared.exe"
if not defined CF if exist "%ProgramFiles(x86)%\cloudflared\cloudflared.exe" set "CF=%ProgramFiles(x86)%\cloudflared\cloudflared.exe"
if not defined CF if exist "%ProgramFiles%\cloudflared\cloudflared.exe" set "CF=%ProgramFiles%\cloudflared\cloudflared.exe"
exit /b 0
