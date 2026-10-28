@echo off
rem ============================================================
rem  UMD - RUN ALL-IN-ONE (double-click file NAY)
rem  Dat trong thu muc goc project, noi CO san: backend\ va requirements.txt
rem  File ten .cmd, KHONG phai .bat/.ps1 -> tranh SmartScreen/AV chan file script
rem  Khong tai gi tu internet, chi dung Python + pip cua may ban.
rem ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist "requirements.txt" (
  echo LOI: Thieu requirements.txt trong: %CD%
  echo Hay copy file nay vao dung thu muc goc project.
  pause & exit /b 1
)
if not exist "backend\main.py" (
  echo LOI: Thieu thu muc backend trong: %CD%
  pause & exit /b 1
)

rem ---- Tim Python 3.10-3.12 ----
set "PYCMD="
for %%V in (3.12 3.11 3.10) do if not defined PYCMD py -%%V -c "pass" >nul 2>nul && set "PYCMD=py -%%V"
if not defined PYCMD python --version 2>nul | findstr /r "Python 3\.1[0-4]" >nul && set "PYCMD=python"
if not defined PYCMD (
  echo LOI: Can Python 3.10 - 3.12. Tai: https://www.python.org/downloads/release/python-3129/
  pause & exit /b 1
)

rem ---- Tao venv neu chua co ----
if not exist ".venv\Scripts\python.exe" (
  echo Dang tao moi truong ao .venv ...
  "!PYCMD!" -m venv .venv || (echo LOI tao venv & pause & exit /b 1)
)
call ".venv\Scripts\activate.bat"

rem ---- Cai dependency ----
echo Dang kiem tra / cai dependency (lan dau mat vai phut) ...
python -m pip install --upgrade pip >nul 2>nul
python -m pip install -r requirements.txt || (echo LOI pip install & pause & exit /b 1)

where ffmpeg >nul 2>nul || echo CANH BAO: FFmpeg chua cai - mot so chuc nang ghep audio/convert se hong.

echo.
echo ============================================
echo  UMD dang chay:  http://127.0.0.1:8756/docs
echo  Health check :  http://127.0.0.1:8756/api/health
echo  Dong cua so CMD nay = ung dung dung.
echo ============================================
start "" http://127.0.0.1:8756/docs
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8756
pause
