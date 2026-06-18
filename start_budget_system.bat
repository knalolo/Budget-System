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

echo Starting Procurement System...
echo Project folder: %cd%
echo Login page: http://127.0.0.1:8000/auth/dev-login/
echo.

start "" "http://127.0.0.1:8000/auth/dev-login/"
python manage.py runserver

endlocal
