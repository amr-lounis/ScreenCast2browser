@echo off
chcp 65001 >nul
echo Installing PyInstaller...
python -m pip install --upgrade pyinstaller >nul
if errorlevel 1 (
  echo Failed to install PyInstaller
  pause
  exit /b 1
)
echo Building portable EXE...
python -m PyInstaller --noconfirm --clean ^
  --onefile ^
  --windowed ^
  --name ScreenCast-browser ^
  --icon NONE ^
  --add-data "config.py;." ^
  --add-data "monitor.py;." ^
  --add-data "capture.py;." ^
  --add-data "server.py;." ^
  --add-data "gui.py;." ^
  --hidden-import dxcam ^
  --hidden-import cv2 ^
  --hidden-import flask ^
  --hidden-import werkzeug ^
  --hidden-import win32api ^
  --hidden-import win32gui ^
  --hidden-import win32con ^
  --collect-all dxcam ^
  --collect-all cv2 ^
  main.py

if errorlevel 1 (
  echo Build failed
  pause
  exit /b 1
)
echo.
echo Build completed: dist\ScreenCast-browser.exe
echo Size:
dir dist\ScreenCast-browser.exe | findstr ScreenCast
pause
