@echo off
chcp 65001 >nul
title J.A.R.V.I.S. — Terminal de Voz & Texto (CMD)
color 0B

echo ============================================================================
echo   J.A.R.V.I.S. — Modo Terminal Interativo (Texto + Voz)
echo   Comandos uteis dentro do chat:
echo     /voice    - Liga/desliga resposta falada do J.A.R.V.I.S.
echo     /listen   - Fala pelo microfone direto no terminal
echo     /ptt      - Modo Push-To-Talk continuo no terminal
echo     /skills   - Lista skills instaladas
echo     /exit     - Encerra a sessao
echo ============================================================================
echo.

set "JARVIS_DIR=%~dp0"
cd /d "%JARVIS_DIR%"
set "PYTHONUTF8=1"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"
set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"

:: Garante que o Ollama esta rodando
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I /N "ollama.exe">NUL
if "%ERRORLEVEL%" NEQ "0" (
    start "Ollama Engine" /MIN "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
    timeout /t 2 /nobreak >nul
)

"%JARVIS_DIR%.venv\Scripts\jarvis.exe" chat --voice
pause
