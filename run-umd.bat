@echo off
rem ============================================================
rem  UMD - RUN ALL-IN-ONE  (double-click file nay)
rem  Dat file NAY vao thu muc goc cua project, noi CO san:
rem      backend\requirements.txt
rem  Duong dan may ban: C:\projectD-acl-out\workspace.tar(3)\universal-media-downloader
rem  File nay tu tim duoc requirements.txt o cung cho voi no, nen
rem  ten thu muc co dau ( ) hay khoang trang deu chay binh thuong.
rem ============================================================
setlocal enabledelayedexpansion

rem --- Di chuyen den thu muc chua file bat nay (thu muc goc project) ---
cd /d "%~dp0"

if not exist "requirements.txt" (
  echo LOI: Khong thay requirements.txt trong:
  echo    %CD%
  echo Hay copy file nay vao THU MUC GOC cua project, tuc la thu muc
  echo chua san folder "backend" va file "requirements.txt".
  echo Neu project cua ban nam sau 1 cap thu muc phat sinh nua, hay di chuot
  echo vao trong do tim dung thu muc goc roi dat file bat o do.
  pause
  exit /b 1
)

if not exist "backend\main.py" (
  echo LOI: Khong thay backend\main.py trong:
  echo    %CD%
  echo Thu muc bat file phai chua folder "backend".
  pause
  exit /b 1
)

echo ==============================================
echo  Universal Media Downloader - Backend setup
echo  Thu muc lam viec : %CD%
echo ==============================================

rem --- Chon interpreter Python 3.10 - 3.12 (uu tien 3.12) ---
set "PYCMD="
for %%V in (3.12 3.11 3.10) do (
  if not defined PYCMD (
    py -%%V -c "pass" >nul 2>nul && set "PYCMD=py -%%V"
  )
)
if not defined PYCMD (
  rem Thu python mac dinh neu no la 3.10 - 3.14
  python --version 2>nul | findstr /r "Python 3\.1[0-4]" >nul && set "PYCMD=python"
)
if not defined PYCMD (
  echo LOI: May ban chua co Python 3.10 - 3.12.
  echo  1) Mo https://www.python.org/downloads/release/python-31210/
  echo  2) Tai "Windows installer (64-bit)", chay, TICH chon "Add python.exe to PATH".
  echo  3) Chay lai file bat nay.
  pause
  exit /b 1
)

echo Dang su dung interpreter:
"!PYCMD!" --version

rem --- Tao virtualenv neu chua co ---
if not exist ".venv\Scripts\python.exe" (
  echo Dang tao virtualenv .venv ^(lan dau, hoi lau^)...
  "!PYCMD!" -m venv .venv
  if errorlevel 1 (
    echo LOI: Khong tao duoc venv. Thu chay: "!PYCMD!" -m venv .venv
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo LOI: Khong activate duoc .venv
  pause
  exit /b 1
)

rem --- Cai dependency (chi lan dau, lan sau rat nhanh) ---
echo Dang kiem tra / cai dependency...
python -m pip install --upgrade pip >nul 2>nul
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo LOI: pip install that bai. Kiem tra mang Internet roi double-click lai file nay.
  pause
  exit /b 1
)

rem --- Kiem tra FFmpeg (khong chan, chi canh bao) ---
where ffmpeg >nul 2>nul || (
  echo ^[CANH BAO^] FFmpeg chua cai. Van tai duoc video don le, nhung ghep
  echo            audio+video hoac doi MP3 se loi. Cai bang lenh:
  echo              winget install Gyan.FFmpeg
)

echo.
echo ==============================================
echo  Backend dang chay:  http://127.0.0.1:8756
echo  Kiem tra khoe:      http://127.0.0.1:8756/api/health
echo  Thu API (Swagger):  http://127.0.0.1:8756/docs
echo  Dung server: Ctrl+C trong cua so nay
echo ==============================================
start "" "http://127.0.0.1:8756/docs"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8756
pause
