@echo off
chcp 65001 >nul
title Setup Jarvis - Asistent vocal
cd /d C:\trading-bot
echo ============================================
echo   Instalare Jarvis (asistent vocal, local)
echo ============================================
echo.
echo [0/5] Curat configul vechi (ca sa se aplice noile setari Jarvis)...
if exist data\voice_bridge.json del /q data\voice_bridge.json
echo.
echo [1/5] Dependinte de baza (STT + microfon + TTS)...
py -m pip install --upgrade pip
py -m pip install faster-whisper sounddevice numpy pyttsx3
echo.
echo [2/5] Wake word "Hey Jarvis" (openWakeWord + onnxruntime)...
py -m pip install openwakeword onnxruntime
echo.
echo [3/5] Voce mai buna (edge-tts - neural, gratuit, optional)...
py -m pip install edge-tts
echo.
echo [4/5] Descarc modelele wake word...
py -c "from openwakeword.utils import download_models; download_models(); print('modele wake OK')"
echo.
echo [5/5] Verificare offline + diagnostic...
py -m voice_bridge.selftest
echo.
py -m voice_bridge.voices
echo.
echo ============================================
echo   Gata. Porneste cu:  start_voice_bridge.bat
echo   Apoi spune:  "Hey Jarvis"  ... "what's the status"
echo   (prima rulare descarca modelul Whisper ~150MB)
echo ============================================
echo.
echo Daca "Hey Jarvis" nu merge, testeaza:
echo   py -m voice_bridge --ptt      (push-to-talk: apesi ENTER, vorbesti)
echo   py -m voice_bridge --debug    (arata tot ce aude)
echo   py -m voice_bridge.miccheck   (diagnostic microfon)
pause >nul
