@echo off
rem Crea dist\MultiROM.exe (no necesita Python instalado para ejecutarse).
rem Requiere: pip install pyinstaller
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --windowed --name MultiROM ^
  --add-data "%~dp0msx\menu.bin;msx" --add-data "%~dp0data\romdb.tsv.gz;data" ^
  --workpath "%TEMP%\multirom_build" --specpath "%TEMP%\multirom_build" ^
  --distpath "%~dp0..\dist" "%~dp0multirom_gui.py"
