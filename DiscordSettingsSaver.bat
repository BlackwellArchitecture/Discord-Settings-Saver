@echo off
title Discord Settings Saver
cd /d "%~dp0"

:: Check if Python is available via 'py' or 'python'
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set PYTHON_CMD=py
    goto check_deps
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set PYTHON_CMD=python
    goto check_deps
)

echo [ERROR] Python 3 was not found on your system!
echo Please install Python 3 (https://www.python.org/) and make sure to check "Add Python to PATH".
echo.
pause
exit /b 1

:check_deps
:: Verify GUI dependencies (CustomTkinter)
%PYTHON_CMD% -c "import customtkinter" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo CustomTkinter is required for the GUI. Installing dependencies...
    %PYTHON_CMD% -m pip install -r "%~dp0requirements.txt"
)

start "" %PYTHON_CMD% "%~dp0main.py"
exit /b 0
