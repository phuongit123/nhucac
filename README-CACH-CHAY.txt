UNIVERSAL MEDIA DOWNLOADER - CACH MO (Windows)
==============================================

Cach don nhat (tranh SmartScreen chan file .bat/.ps1):
  1. Mo CMD (nhan Windows+R, goi "cmd", Enter)
  2. Dan tung dong sau, moi dong nhan Enter:

     cd /d "C:\projectD-acl-out\workspace.tar(3)\universal-media-downloader"
     dir requirements.txt

  Neu "dir" thay requirements.txt -> tiep tuc:

     py -3.12 -m venv .venv
     ".venv\Scripts\activate.bat"
     python -m pip install -r requirements.txt
     python -m uvicorn backend.main:app --host 127.0.0.1 --port 8756

  3. Trinh duyet tu mo (hoac mo tay):
     http://127.0.0.1:8756/docs   <- giao dien thu API (Swagger)
     http://127.0.0.1:8756/api/health  <- kiem tra "status":"ok"

  4. Dung ung dung: nhan Ctrl+C trong CMD hoac dong cua so CMD.

Neu py -3.12 khong tim thay: thu "py -3.11", "py -3.10" hoac "python".
Neu yeu cau double-click: dung file run-umd.cmd (ten .cmd it bi SmartScreen
chan hon .bat). Van bi chan thi chuot phai file > Properties > Unblock > OK.

Test nhanh (tuy chon):
     python -m pytest backend/tests/test_config_db.py backend/tests/test_engine.py -v
