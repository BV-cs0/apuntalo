@echo off
rem Vuelve a generar Apuntalo.exe (necesita: py -3 -m pip install pyinstaller anthropic)
cd /d "%~dp0"
py -3 -m PyInstaller --noconfirm --onefile --windowed --name Apuntalo --icon "%~dp0apuntes.ico" --add-data "%~dp0captura.ps1;." --distpath . --workpath "%TEMP%\apuntes_build" --specpath "%TEMP%\apuntes_build" --paths "%~dp0." "%~dp0apuntes.pyw"
pause
