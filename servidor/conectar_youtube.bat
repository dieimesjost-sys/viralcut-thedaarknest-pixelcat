@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Conectando sua conta do YouTube para postagem automatica de Shorts...
echo Certifique-se de ter colocado o arquivo client_secrets.json nesta pasta.
echo.
python youtube_uploader.py
pause
