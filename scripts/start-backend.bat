@echo off
rem Khoi dong backend UMD. Chay tu thu muc goc cua project sau khi da setup.
cd /d %~dp0..
if not exist ".venv\Scripts\python.exe" (
  echo Chua co virtualenv. Hay chay: powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8756
pause
