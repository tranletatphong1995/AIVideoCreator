@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Fooocus API Engine

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_NO_COLOR=1"
set "PIP_PROGRESS_BAR=off"

cd /d "%~dp0" || goto :fatal_cwd

set "VENV_DIR=.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "HOST=127.0.0.1"
set "PORT=8888"

if not "%~1"=="" set "HOST=%~1"
if not "%~2"=="" set "PORT=%~2"
if /I "%~1"=="--check" (
    echo ============================================
    echo   Fooocus API Engine - Check
    echo ============================================
    echo Folder: %CD%
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3.10 -c "import sys; print('Python 3.10:', sys.executable)"
        if errorlevel 1 (
            echo [ERR] Python 3.10 was not found by py launcher.
            exit /b 1
        )
    ) else (
        where python >nul 2>nul
        if errorlevel 1 (
            echo [ERR] Python was not found.
            exit /b 1
        )
        python -c "import sys; print('Python:', sys.executable)"
    )
    if exist "%VENV_PY%" (
        echo [OK] Fooocus API venv exists: %VENV_PY%
    ) else (
        echo [INFO] Fooocus API venv not created yet. It will be created on first API start.
    )
    exit /b 0
)

echo ============================================
echo   Fooocus API Engine
echo ============================================
echo Folder: %CD%
echo URL:    http://%HOST%:%PORT%
echo.

if not exist "%VENV_PY%" (
    call :create_venv || goto :fatal
) else (
    echo [OK] Fooocus API virtual environment found.
)

echo.
echo [*] Checking bootstrap packages...
"%VENV_PY%" -m pip install --disable-pip-version-check --no-color --progress-bar off colorlog
if errorlevel 1 goto :fatal

echo.
echo [*] Starting Fooocus API...
echo     First launch can take a long time because dependencies and SDXL models may be downloaded.
echo.
"%VENV_PY%" main.py --host %HOST% --port %PORT%
set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo [!] Fooocus API stopped with exit code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%

:create_venv
echo [*] Creating Fooocus API virtual environment...
where py >nul 2>nul
if not errorlevel 1 (
    py -3.10 -m venv "%VENV_DIR%"
) else (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -m venv "%VENV_DIR%"
    ) else (
        echo [ERR] Python was not found.
        echo       Install Python 3.10 or 3.11, then run this file again.
        exit /b 1
    )
)
if not exist "%VENV_PY%" (
    echo [ERR] Could not create Fooocus API virtual environment.
    echo       Recommended: install Python 3.10 x64.
    exit /b 1
)
echo [OK] Fooocus API virtual environment created.
exit /b 0

:fatal_cwd
echo [ERR] Could not switch to the Fooocus API folder.
pause
exit /b 1

:fatal
echo.
echo [ERR] Fooocus API setup/start failed. Please read the messages above.
pause
exit /b 1
