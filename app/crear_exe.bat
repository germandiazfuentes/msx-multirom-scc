@echo off
rem Crea dist\MultiROM.exe (no necesita Python instalado para ejecutarse).
rem Requiere: pip install pyinstaller
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --windowed --name MultiROM ^
  --icon "%~dp0data\calamar.ico" ^
  --add-data "%~dp0msx\menu.bin;msx" --add-data "%~dp0data\romdb.tsv.gz;data" ^
  --add-data "%~dp0data\calamar.ico;data" --add-data "%~dp0data\calamar.png;data" ^
  --workpath "%TEMP%\multirom_build" --specpath "%TEMP%\multirom_build" ^
  --distpath "%~dp0..\dist" "%~dp0multirom_gui.py"
