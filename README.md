# ScreenCast->browser

Stream any monitor to any browser on your local network. No client install required.

> Full name: **ScreenCast 2 browser** — short: `ScreenCast->browser`

## Features
- High-performance capture via DXGI (`dxcam`)
- Auto-detect monitors with resolution
- Adjustable FPS / Quality / Cursor
- Access code protection (`1234` by default)
- Auto-reconnect on disconnect
- Color-correct streaming

## Structure
```
main.py              # entry point
config.py            # settings
monitor.py           # monitor discovery
capture.py           # frame generation
server.py            # Flask app
gui.py               # Tkinter UI
```

## Requirements
- Windows 10/11, Python 3.11+

```bat
pip install -r requirements.txt
```

## Run
```bat
python main.py
```
Select monitor → Start Server → open `http://IP:PORT/?code=1234`

- With code: `http://IP:8080/?code=1234`
- Without code: leave field empty

## Build EXE (portable)

```bat
build.bat
```
Output: `dist/ScreenCast-browser.exe` (single file, 80-150 MB)

Manual:
```bat
pip install pyinstaller
pyinstaller --onefile --windowed --name ScreenCast-browser main.py
# debug with console:
pyinstaller --onefile --console --name ScreenCast-browser_debug main.py
```

## Config
Edit `config.py` or use GUI:
```python
"fps": 30, "quality": 70, "show_cursor": True, "access_code": "1234"
```

## License
MIT
