@echo off
cd /d "%~dp0"

:: Activate Environment
IF EXIST "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
) ELSE IF EXIST ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

:: Run the Python Launcher
python launcher.py