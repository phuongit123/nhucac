@echo off
rem ============================================================
rem  UMD - Cai dat + khoi dong backend (chay bang CMD, double-click duoc)
rem  Tu phat hien Python 3.10-3.12, khong dung Python 3.15 cua may neu ban 3.12 ton tai.
rem  Duong dan co dau ( ) va khoang trang da duoc boc trong ngoac kep day du.
rem ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0.."

if not exist requirements.txt (
  echo LOI: Khong tim thay requirements.txt. Chay file nay nam trong thu muc scripts\ cua project.
  pause & exit /b 1
)

rem --- Chon interpreter: uu tien 3.12, 3.11, 3.10; tranh 3.15 ---
set "PYCMD="
for %%V in (3.12 3.11 3.10) do (
  if not defined PYCMD (
    py -%%V -c "pass" >nul 2>nul && set "PYCMD=py -%%V"
  )
)
if not defined PYCMD (
  python --version 2>nul | findstr /r "Python 3\.1[0-4]" >nul && set "PYCMD=python"
)
if not defined PYCMD (
  echo LOI: Can Python 3.10-3.12. Hien may chi co ban qua moi hoac qua cu.
  echo Cai Python 3.12 tu https://www.python.org/downloads/ roi chay lai file nay.
  pause & exit /b 1
)
echo Dang su dung: !PYCMD!
"!PYCMD!" --version

if not exist ".venv\Scripts\python.exe" (
  echo Tao virtualenv .venv ...
  "!PYCMD!" -m venv .venv || (echo LOI tao venv & pause & exit /b 1)
)
call ".venv\Scripts\activate.bat" || (echo LOI activate venv & pause & exit /b 1)

echo Nang cap pip...
python -m pip install --upgrade pip >nul

echo Cai dependency (lan dau mat vai phut)...
python -m pip install -r requirements.txt || (echo LOI pip install - kiem tra mang roi chay lai & pause & exit /b 1)

echo Kiem tra FFmpeg...
where ffmpeg >nul 2>nul || echo CANH BAO: FFmpeg chua cai. Tai van chay duoc nhung ghep video+audio se loi. Cai: winget install Gyan.FFmpeg

echo Khoi dong backend tai http://127.0.0.1:8756  (Ctrl+C de dung)
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8756
pause
