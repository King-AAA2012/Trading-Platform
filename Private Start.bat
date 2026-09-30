@echo off
rem Runs CasuallyHedge just for you: no sign-up, login, trial or payments.
rem Your data lives in data\state.json on this PC. Only this computer can open it (127.0.0.1).
set CH_PRIVATE=1
set CH_HOST=127.0.0.1
title CasuallyHedge (private)
call "%~dp0start.bat"
