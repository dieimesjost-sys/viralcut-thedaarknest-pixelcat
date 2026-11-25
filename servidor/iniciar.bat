@echo off
chcp 65001 >nul
cd /d "%~dp0"
if "%GEMINI_API_KEY%"=="" set GEMINI_API_KEY=SUA_CHAVE_GEMINI_AQUI
if "%PIXABAY_API_KEY%"=="" set PIXABAY_API_KEY=SUA_CHAVE_PIXABAY_AQUI
set PEXELS_API_KEY=
set WHISPER_MODEL=small
echo ======================================================
echo   VIRALCUT AI v2.4 + AGENTE DARK (theDaarkNest)
echo   Servidor rodando em http://0.0.0.0:8000
echo ======================================================
python -m uvicorn server:app --host 0.0.0.0 --port 8000
pause
