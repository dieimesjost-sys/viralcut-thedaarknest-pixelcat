@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Instalando todas as dependencias do ViralCut AI v2.1 (YT + IG + TikTok Studio)...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Instalando navegador Chromium para automacao do TikTok Studio...
python -m playwright install chromium
echo.
echo Instalacao concluida! Agora edite o arquivo iniciar.bat com sua chave Gemini.
pause
