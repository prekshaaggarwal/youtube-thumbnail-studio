@echo off
setlocal EnableDelayedExpansion
title Thumbnail Studio Launcher
cd /d "%~dp0"

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if defined PY goto have_py

where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [1/5] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Could not create .venv. Install Python 3 from https://www.python.org/downloads/
        echo During setup, enable "Add python.exe to PATH", then run this file again.
        pause
        exit /b 1
    )
    set "PY=%~dp0.venv\Scripts\python.exe"
) else (
    echo ERROR: Python was not found in PATH.
    echo Install Python 3 from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
    pause
    exit /b 1
)

:have_py
echo [2/5] Using: %PY%
"%PY%" --version

echo [3/5] Installing dependencies...
"%PY%" -m pip install -q --upgrade pip
"%PY%" -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed. Check internet connection.
    pause
    exit /b 1
)

echo [4/5] Checking port 8080 (stops stale Python servers that cause /studio 404)...
set "FORCE_ALT_PORT="
"%PY%" "%~dp0scripts\port_8080.py"
set "PREF=%ERRORLEVEL%"
if "%PREF%"=="4" goto already_running
if "%PREF%"=="2" set "FORCE_ALT_PORT=1"

set "APP_PORT=8080"
if defined FORCE_ALT_PORT (
    echo.
    echo Port 8080 still unavailable — using 8765 instead.
    set APP_PORT=8765
) else (
    netstat -ano | findstr ":8080 " | findstr "LISTENING" >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        echo.
        echo WARNING: Something is already using port 8080.
        echo Trying port 8765 instead.
        set APP_PORT=8765
    )
)

echo [5/5] Starting server on port %APP_PORT% in a separate window...
echo.
echo    >>>  http://127.0.0.1:%APP_PORT%/
echo    >>>  Create your thumbnail:  http://127.0.0.1:%APP_PORT%/studio
echo.
set APP_HOST=127.0.0.1
start "Thumbnail Studio Server" "%~dp0scripts\server-window.bat" %APP_PORT%
echo Waiting until the server answers (up to 90 seconds)...
"%PY%" "%~dp0scripts\wait_for_health.py" %APP_PORT%
set "WH=%ERRORLEVEL%"
if not "%WH%"=="0" (
    echo.
    echo ERROR: Server did not start. Read the window titled "Thumbnail Studio Server" for Python errors.
    pause
    exit /b 1
)
if not "%TSG_BROWSER_OPEN%"=="0" (
    echo Opening /studio in your default browser...
    "%PY%" -c "import webbrowser; webbrowser.open('http://127.0.0.1:%APP_PORT%/studio')"
)
echo.
echo ======================================================================
echo   RUNNING: separate window titled "Thumbnail Studio Server"
echo   Use that window to see logs. CLOSE ONLY THAT WINDOW to stop the site.
echo   This launcher is safe to close — it does NOT stop the server.
echo ======================================================================
echo.
pause
exit /b 0

:already_running
echo.
echo No new server was started — use the URLs above.
if not "%TSG_BROWSER_OPEN%"=="0" (
    start /b "" "%PY%" -c "import webbrowser; webbrowser.open('http://127.0.0.1:8080/studio')"
)
pause
exit /b 0
