@echo off
setlocal EnableExtensions
chcp 65001 >nul
title AI Video Creator

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "VIENEU_EXTRA_INDEX=https://pnnbao97.github.io/llama-cpp-python-v0.3.16/cpu/"

cd /d "%~dp0" || goto :fatal_cwd

set "VENV_DIR=.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "QT_QPA_PLATFORM_PLUGIN_PATH=%CD%\.venv\Lib\site-packages\PyQt5\Qt5\plugins"
set "QT_PLUGIN_PATH=%CD%\.venv\Lib\site-packages\PyQt5\Qt5\plugins"

echo ============================================
echo   AI Video Creator - One Click Launcher
echo ============================================
echo Folder: %CD%
echo.

if not exist "%VENV_PY%" (
    call :create_venv || goto :fatal
    call :install_deps || goto :fatal
) else (
    echo [OK] Virtual environment found
)

echo.
echo [*] Checking environment...
"%VENV_PY%" check_environment.py
if errorlevel 1 (
    echo.
    echo [*] Environment incomplete. Repairing automatically...
    call :install_deps || goto :fatal
    echo.
    echo [*] Re-checking environment...
    "%VENV_PY%" check_environment.py
    if errorlevel 1 goto :fatal_env
)

if /I "%~1"=="--check" (
    echo.
    echo [OK] Launcher check completed. App was not started because --check was used.
    exit /b 0
)

echo.
echo [OK] Starting AI Video Creator...
"%VENV_PY%" main_ui.py
set "APP_EXIT=%ERRORLEVEL%"
echo.
if not "%APP_EXIT%"=="0" (
    echo [!] AI Video Creator closed with exit code %APP_EXIT%.
    pause
)
exit /b %APP_EXIT%

:create_venv
echo [*] Virtual environment not found. Creating .venv...
call :create_venv_with_available_python
if errorlevel 1 (
    echo [WARN] Python was not found or could not create a venv.
    echo        Trying to install Python 3.11 with winget...
    call :install_python || exit /b 1
    call :create_venv_with_available_python
)
if errorlevel 1 (
    echo [ERR] Python is installed, but this terminal cannot see it yet.
    echo       Close this window and run run.bat again.
    exit /b 1
)
if not exist "%VENV_PY%" (
    echo [ERR] Could not create virtual environment.
    exit /b 1
)
echo [OK] Virtual environment created.
exit /b 0

:create_venv_with_available_python
where py >nul 2>nul
if not errorlevel 1 (
    py -3.11 -m venv "%VENV_DIR%"
    if errorlevel 1 py -3.10 -m venv "%VENV_DIR%"
    if errorlevel 1 py -3 -m venv "%VENV_DIR%"
    if errorlevel 1 exit /b 1
    exit /b 0
) else (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -m venv "%VENV_DIR%"
        if errorlevel 1 exit /b 1
        exit /b 0
    ) else (
        where python3 >nul 2>nul
        if not errorlevel 1 (
            python3 -m venv "%VENV_DIR%"
            if errorlevel 1 exit /b 1
            exit /b 0
        ) else (
            if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
                "%LocalAppData%\Programs\Python\Python311\python.exe" -m venv "%VENV_DIR%"
                if errorlevel 1 exit /b 1
                exit /b 0
            )
            if exist "%ProgramFiles%\Python311\python.exe" (
                "%ProgramFiles%\Python311\python.exe" -m venv "%VENV_DIR%"
                if errorlevel 1 exit /b 1
                exit /b 0
            )
            exit /b 1
        )
    )
)

:install_python
where winget >nul 2>nul
if errorlevel 1 (
    echo [ERR] Python was not found and winget is unavailable.
    echo       Install Python 3.10+ manually and tick "Add python.exe to PATH".
    exit /b 1
)
winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo [ERR] Could not install Python 3.11 with winget.
    exit /b 1
)
exit /b 0

:install_deps
echo [*] Installing/updating Python dependencies...
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 exit /b 1
"%VENV_PY%" -m pip install -r requirements.txt --extra-index-url "%VIENEU_EXTRA_INDEX%"
if errorlevel 1 exit /b 1
echo [*] Installing Playwright Chromium...
"%VENV_PY%" -m playwright install chromium
if errorlevel 1 exit /b 1
echo [OK] Dependencies are ready.
exit /b 0

:fatal_env
echo.
echo [ERR] Environment is still incomplete after repair.
echo      Please read the messages above, then run this file again.
pause
exit /b 1

:fatal_cwd
echo [ERR] Could not switch to the launcher folder.
pause
exit /b 1

:fatal
echo.
echo [ERR] Setup failed. Please read the messages above, then run this file again.
pause
exit /b 1
