@echo off
:: Inlocuit de setup.bat --with-ai (instalarea completa + Ollama + modelul AI Engine).
:: Pastrat ca scurtatura; verificarile AI: py -m ai_engine.selftest / py -m ai_engine.doctor
call "%~dp0setup.bat" --with-ai %*
