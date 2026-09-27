@echo off
setlocal EnableExtensions

rem Digital Marketing KPI Dashboard + Cloudflare Tunnel launcher
set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=%PROJECT_DIR%.venv\Scripts\python.exe"
set "APP_FILE=%PROJECT_DIR%app.py"
set "DATA_DIR=%PROJECT_DIR%..\数据底表V1"
set "PORT=8050"
set "TUNNEL_CONFIG=%PROJECT_DIR%dashboard-tunnel.yml"
set "PUBLIC_HOST=dashboard.chengying-she.top"

title Dashboard and Cloudflare Tunnel

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Project virtual environment was not found:
    echo         %PYTHON_EXE%
    pause
    exit /b 1
)

if not exist "%APP_FILE%" (
    echo [ERROR] app.py was not found:
    echo         %APP_FILE%
    pause
    exit /b 1
)

where cloudflared >nul 2>&1
if errorlevel 1 (
    echo [ERROR] cloudflared is not installed or is not on PATH.
    echo Install it first, then run: cloudflared tunnel login
    pause
    exit /b 1
)

if not exist "%TUNNEL_CONFIG%" (
    echo [ERROR] Tunnel configuration was not found:
    echo         %TUNNEL_CONFIG%
    pause
    exit /b 1
)

echo [INFO] Starting Dash on http://127.0.0.1:%PORT% ...
start "Dashboard App" /D "%PROJECT_DIR%" cmd /k ""%PYTHON_EXE%" "%APP_FILE%" --data-dir "%DATA_DIR%" --port %PORT%"

echo [INFO] Waiting for the local dashboard to listen on port %PORT% ...
set /a WAIT_COUNT=0
:wait_for_app
powershell -NoProfile -ExecutionPolicy Bypass -Command "$c = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue; if ($c) { exit 0 } else { exit 1 }"
if not errorlevel 1 goto app_ready
set /a WAIT_COUNT+=1
if %WAIT_COUNT% GEQ 30 (
    echo [ERROR] Dashboard did not start within 30 seconds.
    echo Check the Dashboard App window for the Python error.
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait_for_app

:app_ready
echo [INFO] Dashboard is ready.
echo [INFO] Public URL: https://%PUBLIC_HOST%
echo [INFO] Starting Cloudflare Tunnel ...
cloudflared tunnel --config "%TUNNEL_CONFIG%" run

endlocal