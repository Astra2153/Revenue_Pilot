@echo off
echo Starting RevenuePilot backend and frontend...

REM %~dp0 = the folder this .bat file lives in (Root), regardless of where you double-click it from.
start "RevenuePilot Backend" cmd /k "cd /d "%~dp0" && python -m uvicorn api.api:app --reload --port 8000"
start "RevenuePilot Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo Both servers are starting in separate windows.
echo Waiting a few seconds for the frontend to be ready...
timeout /t 5 /nobreak >nul

start http://localhost:5173

echo Done. Two terminal windows are now running your backend and frontend.
echo Close this window any time -- it does not need to stay open.
pause
