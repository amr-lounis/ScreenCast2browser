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
REM Phase 4: no OpenCV - use simplejpeg + Pillow (lean)
python -m PyInstaller --noconfirm --clean ^
  --onefile ^
  --windowed ^
  --name ScreenCast-browser ^
  --icon NONE ^
  --hidden-import dxcam ^
  --hidden-import simplejpeg ^
  --hidden-import PIL ^
  --hidden-import flask ^
  --hidden-import werkzeug ^
  --hidden-import win32api ^
  --hidden-import win32gui ^
  --hidden-import win32con ^
  --collect-all dxcam ^
  --collect-all simplejpeg ^
  --collect-all PIL ^
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
