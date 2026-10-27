@echo off
chcp 65001 >nul
title J.A.R.V.I.S. — Aplicativo Desktop Electron (Maestro HUB)
color 0B

set "JARVIS_DIR=%~dp0"
cd /d "%JARVIS_DIR%electron"

echo Iniciando Aplicativo Desktop Nativo J.A.R.V.I.S. (Electron + Google Gemini API + Argon Maestro)...
start "" "%JARVIS_DIR%electron\node_modules\electron\dist\electron.exe" "%JARVIS_DIR%electron"
