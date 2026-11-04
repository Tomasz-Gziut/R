@echo off
setlocal
cd /d "%~dp0"

tasklist /FI "IMAGENAME eq ScreenshotHotkey.exe" /NH | find /I "ScreenshotHotkey.exe" >nul
if not errorlevel 1 (
    echo Close ScreenshotHotkey.exe before rebuilding.
    exit /b 1
)

py -m pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b %errorlevel%

py -m PyInstaller --clean --noconfirm --onefile --console --add-data "assets\replay_button.png;assets" --name ScreenshotHotkey screenshot.py
if errorlevel 1 exit /b %errorlevel%

copy /Y "dist\ScreenshotHotkey.exe" "ScreenshotHotkey.exe" >nul
if errorlevel 1 exit /b %errorlevel%

echo Built ScreenshotHotkey.exe
