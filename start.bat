@echo off
title TradeScope
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
where ollama >nul 2>nul && (start "" /min ollama serve)
start "" http://127.0.0.1:8420/
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8420
