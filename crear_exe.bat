@echo off
rem Vuelve a generar Apuntalo.exe (necesita: py -3 -m pip install pyinstaller anthropic pyspellchecker)
cd /d "%~dp0"
py -3 -m PyInstaller --noconfirm --onefile --windowed --name Apuntalo --icon "%~dp0apuntalo\apuntalo.ico" --add-data "%~dp0apuntalo\captura.ps1;apuntalo" --add-data "%~dp0apuntalo\apuntalo.ico;apuntalo" --distpath . --workpath "%TEMP%\apuntes_build" --specpath "%TEMP%\apuntes_build" --collect-data spellchecker --paths "%~dp0." "%~dp0apuntes.pyw"
pause
