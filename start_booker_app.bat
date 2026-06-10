@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    ".venv\Scripts\pythonw.exe" booker_app.py
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" booker_app.py
) else (
    python booker_app.py
)
