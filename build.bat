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
REM Phase 3: removed redundant --add-data for .py files (auto-discovered via imports)
python -m PyInstaller --noconfirm --clean ^
  --onefile ^
  --windowed ^
  --name ScreenCast-browser ^
  --icon NONE ^
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
