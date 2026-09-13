@echo off
setlocal
cd /d "%~dp0"

REM Creates dist\ACMP\ACMP.exe. One-folder mode is more reliable for Qt WebEngine.
py -3.12 -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error

py -3.12 -m PyInstaller --noconfirm --clean --windowed --name ACMP --collect-all PySide6 --collect-all shapely main.py
if errorlevel 1 goto :error

echo.
echo Build complete: dist\ACMP\ACMP.exe
pause
exit /b 0

:error
echo.
echo Build failed. Check the messages above.
pause
exit /b 1
