@echo off
rem Reensambla el menu del MSX (necesita pasmo.exe en la carpeta superior o en el PATH)
cd /d "%~dp0msx"
if exist "..\..\pasmo.exe" (set PASMO=..\..\pasmo.exe) else (set PASMO=pasmo)
%PASMO% menu.asm menu.bin menu.sym
