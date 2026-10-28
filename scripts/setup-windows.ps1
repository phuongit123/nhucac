# Universal Media Downloader - Setup & Run (Windows PowerShell)
# Chay: powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))

Write-Host "== UMD setup ==" -ForegroundColor Cyan

# 1. Tim Python 3.10-3.12 khong phai Microsoft Store stub
$py = $null
foreach ($c in @("python3.12","python3.11","python3.10","python","py")) {
    $v = & $c -c "import sys;print('%d.%d'%sys.version_info[:2])" 2>$null
    if ($LASTEXITCODE -eq 0 -and $v) {
        $maj, $min = $v.Split(".")
        if ([int]$maj -eq 3 -and [int]$min -ge 10 -and [int]$min -le 12) { $py = $c; break }
        elseif ([int]$maj -eq 3 -and [int]$min -ge 13) { if (-not $py) { $py = $c } }
    }
}
if (-not $py) { Write-Host "Khong tim thay Python 3.10+. Cai tai https://www.python.org/downloads/ (tich 'Add to PATH')." -ForegroundColor Red; exit 1 }
Write-Host "Su dung Python qua lenh: $py"

# 2. venv trong thu muc du an (KHONG dung dau ; tren dong lenh gộp)
if (-not (Test-Path ".venv")) { & $py -m venv .venv }
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

# 3. Kiem tra FFmpeg va yt-dlp
$ff = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($ff) { Write-Host "FFmpeg: $($ff.Source)" -ForegroundColor Green }
else { Write-Host "CHU Y: FFmpeg chua cai. Tai video kem am thanh se loi. Cai: winget install Gyan.FFmpeg" -ForegroundColor Yellow }
& ".\.venv\Scripts\python.exe" -c "import yt_dlp; print('yt-dlp OK')"

# 4. Chay test
& ".\.venv\Scripts\python.exe" -m pytest backend/tests/test_config_db.py backend/tests/test_engine.py

# 5. Ghi file bat nhanh de start
@"
@echo off
cd /d "%~dp0.."
".venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8756
pause
"@ | Set-Content -Encoding ASCII scripts\start-backend.bat
Write-Host "Xong! Bat backend:  .\scripts\start-backend.bat" -ForegroundColor Green
