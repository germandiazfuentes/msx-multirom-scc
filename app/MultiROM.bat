@echo off
rem Lanza el generador de MultiROM MSX
cd /d "%~dp0"
start "" pythonw multirom_gui.py %*
