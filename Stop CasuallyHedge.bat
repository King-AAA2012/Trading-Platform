@echo off
rem Stops a CasuallyHedge server started by start.bat or the no-window launcher.
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":8420 .*LISTENING"') do taskkill /F /PID %%p >nul 2>nul
wmic process where "CommandLine like '%%uvicorn backend.app%%'" call terminate >nul 2>nul
echo CasuallyHedge stopped.
timeout /t 2 >nul
