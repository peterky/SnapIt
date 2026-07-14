@echo off
cd /d "%~dp0"
if not exist .venv python -m venv .venv
call .venv\Scripts\python.exe -m pip install -q -r requirements.txt
start "" .venv\Scripts\pythonw.exe -m snapit