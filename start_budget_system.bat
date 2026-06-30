@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [Error] Virtual environment not found at .venv\Scripts\python.exe
    echo Please check whether the project environment is set up correctly.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [Error] Failed to activate the virtual environment.
    pause
    exit /b 1
)

set "LAN_IP=127.0.0.1"
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\get-lan-ip.ps1"`) do set "LAN_IP=%%I"

echo Starting Procurement System...
echo Project folder: %cd%
echo Local login page: http://127.0.0.1:8000/auth/dev-login/
echo LAN login page:   http://%LAN_IP%:8000/auth/dev-login/
echo.
echo Keep this window open while the website is in use.
echo Other computers must be on the same company network.
echo If Windows Firewall asks for permission, allow access on Private networks.
echo.

start "" "http://127.0.0.1:8000/auth/dev-login/"
python manage.py runserver 0.0.0.0:8000

endlocal
