@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
py -3 -m venv .venv
if errorlevel 1 goto fallback
if exist ".venv\Scripts\python.exe" goto install
:fallback
python -m venv .venv
if errorlevel 1 goto failed
:install
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if errorlevel 1 goto failed
echo.
echo Open http://127.0.0.1:8000 in your browser after the server starts.
echo Press Ctrl+C to stop the server.
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Setup or startup failed. Check the error above. Python 3.12 or newer is required.
pause
exit /b 1
