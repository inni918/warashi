@echo off
REM ===========================================================================
REM Warashi - Windows launcher (double-clickable)
REM ---------------------------------------------------------------------------
REM Double-click this file to start your companion.
REM
REM What it does:
REM   1. Makes sure `uv` (the Python package manager) is installed.
REM   2. Installs/updates dependencies with `uv sync`.
REM   3. Opens your browser to the app.
REM   4. Starts the server (run_server.py).
REM This is also your DAILY launcher - just run it every time.
REM ===========================================================================

setlocal enableextensions
title Warashi

REM Always run from the folder this script lives in (the project root).
cd /d "%~dp0"

set "APP_URL=http://localhost:12393"

echo ============================================================
echo   Warashi - starting up
echo ============================================================
echo.

REM --- 1. Ensure uv is installed -------------------------------------------
where uv >nul 2>&1
if %ERRORLEVEL%==0 goto have_uv

REM uv might be installed at the default per-user location but not on PATH.
if exist "%USERPROFILE%\.local\bin\uv.exe" (
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
where uv >nul 2>&1
if %ERRORLEVEL%==0 goto have_uv

echo   'uv' is not installed. Installing it now (one-time)...
echo   (uv is a fast Python package manager from Astral.)
echo.
powershell -ExecutionPolicy ByPass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

where uv >nul 2>&1
if %ERRORLEVEL%==0 goto have_uv

echo.
echo   ERROR: uv still isn't available after install.
echo   Close this window, open a new Command Prompt, and run this file again.
echo   Or install manually: https://docs.astral.sh/uv/getting-started/installation/
echo.
pause
exit /b 1

:have_uv
for /f "delims=" %%i in ('where uv') do set "UV_PATH=%%i"
echo   uv found: %UV_PATH%
echo.

REM --- 2. Install / update dependencies ------------------------------------
echo   Installing dependencies (uv sync) - first run can take a few minutes...
call uv sync
if %ERRORLEVEL% neq 0 (
  echo.
  echo   ERROR: 'uv sync' failed. Scroll up for details.
  echo.
  pause
  exit /b 1
)
echo   Dependencies ready.
echo.

REM --- First run: create conf.yaml from the default template if it's missing -
if not exist "conf.yaml" (
  copy /Y "config_templates\conf.warashi.default.yaml" "conf.yaml" >nul
  echo   Created conf.yaml from the default template.
  echo.
)

REM --- 3. Start the server (it opens the browser itself once it's READY) ---
REM NOTE: we do NOT open the browser here. run_server.py --open-browser waits
REM until the server is actually listening before opening %APP_URL%, so a slow
REM first-run startup (speech-model download) never shows a "connection refused"
REM page. The browser pops up on its own once everything is ready.
echo ============================================================
echo   Server starting. Leave THIS WINDOW OPEN while you chat.
echo   First launch: a small speech model downloads automatically, so the
echo   browser may take a minute to open by itself - that is normal.
echo.
echo   If it does not open on its own, browse to %APP_URL% manually.
echo.
echo   On first run a setup wizard appears in the browser - paste an
echo   API key (OpenAI / Claude / Gemini) OR pick a local Ollama model.
echo.
echo   To quit: close this window (or press Control-C).
echo ============================================================
echo.
call uv run run_server.py --open-browser

echo.
echo   Server stopped.
pause
