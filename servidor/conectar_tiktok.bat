@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ======================================================
echo   CONECTAR TIKTOK STUDIO (LOGIN UNICO)
echo   Faca login na janela que vai abrir e depois feche-a.
echo ======================================================
python tiktok_uploader.py
pause
