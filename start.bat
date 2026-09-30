@echo off
title CasuallyHedge
cd /d "%~dp0"
echo.
echo  CasuallyHedge - Trading, for the little guy.  (beta)
echo.

where python >nul 2>nul || (
  echo  Python is required ^(free^). Install it from https://www.python.org/downloads/ and tick "Add to PATH".
  echo  Or run:  winget install Python.Python.3.12
  if defined TS_HIDDEN exit /b 1
  pause & exit /b 1
)
python -m pip install -q -r requirements.txt

rem ---- free local AI (optional). Everything else works without it.
where ollama >nul 2>nul
if errorlevel 1 (
  echo  The AI analyst uses Ollama, a free local AI runtime. It is not installed.
  if not defined TS_HIDDEN choice /c YN /m "  Install Ollama now with winget (free, about 1 GB)"
  if not defined TS_HIDDEN if not errorlevel 2 winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
)
where ollama >nul 2>nul
if not errorlevel 1 (
  start "" /min ollama serve
  timeout /t 3 >nul
  ollama list 2>nul | findstr /i "llama3.1 qwen2.5 llama3 mistral" >nul
  if errorlevel 1 (
    echo  Downloading the free Llama 3.1 8B model ^(about 4.9 GB, one time only^)...
    ollama pull llama3.1:8b
  )
)

rem ---- stop any older CasuallyHedge server still holding port 8420, so the latest version always runs
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":8420 .*LISTENING"') do taskkill /F /PID %%p >nul 2>nul

start "" http://127.0.0.1:8420/
echo.
echo  CasuallyHedge is running at http://127.0.0.1:8420  -  keep this window open (minimise it).
echo  Close this window to stop CasuallyHedge.
echo.
:serve
if not defined CH_HOST set CH_HOST=127.0.0.1
python -m uvicorn backend.app:app --host %CH_HOST% --port 8420 --proxy-headers
echo  Server stopped unexpectedly - restarting in 3 seconds...
timeout /t 3 >nul
goto serve
