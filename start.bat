@echo off
title TradeScope
cd /d "%~dp0"
echo.
echo  TradeScope - 100%% free, runs on your own PC. No accounts, no API keys, no subscriptions.
echo.

where python >nul 2>nul || (
  echo  Python is required ^(free^). Install it from https://www.python.org/downloads/ and tick "Add to PATH".
  echo  Or run:  winget install Python.Python.3.12
  pause & exit /b 1
)
python -m pip install -q -r requirements.txt

rem ---- free local AI (optional). Everything else works without it.
where ollama >nul 2>nul
if errorlevel 1 (
  echo  The AI analyst uses Ollama, a free local AI runtime. It is not installed.
  choice /c YN /m "  Install Ollama now with winget (free, about 1 GB)"
  if not errorlevel 2 winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
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

start "" http://127.0.0.1:8420/
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8420
