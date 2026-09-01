# ScreenCast->browser

ScreenCast 2 browser — stream desktop to any device browser on the same network, no install needed. Captures via DXGI (dxcam) and streams MJPEG via Flask, with monitor selection, FPS/quality control, access code protection and auto-reconnect on disconnect.

![GUI](readme/01.JPG)

## Run
```bat
pip install -r requirements.txt
python main.py
```
Open `http://IP:PORT/?code=1234` (default code `1234`, or click **Gen** for random)

![Browser](readme/02.JPG)

## Features
- **Monitor selection** with live Win32 detection + dxcam fallback, dynamic offset (no hardcoded 1920)
- **FPS/Quality** slider with perf_counter-based timing (no extra frame copy)
- **Access code** protection: `secrets.compare_digest`, header `X-Access-Code` support, 10/min rate-limit (429)
- **Streaming resilience**: abort-previous on reconnect, exponential backoff, `naturalWidth` stall detection, `visibilitychange` resume
- **Thread-safe**: `RLock` + `Event` for camera/server, port busy pre-check via `SO_REUSEADDR=0`
- **Structured code** (Phase 3): `gui.App` class, `StreamConfig` TypedDict, `logging` instead of silent `except: pass`

## Build EXE
```bat
build.bat
```
Output: `dist/ScreenCast-browser.exe` (~77MB, PyInstaller 6.22.2, no redundant add-data)

`ScreenCast-browser.spec` uses `collect_all` only - py files auto-discovered via imports.

## Tip: Extend Display to Any Browser Device
Use https://github.com/VirtualDrivers/Virtual-Display-Driver to create a virtual monitor, then select it in ScreenCast->browser to extend your desktop to any device with a web browser (phone, tablet, TV).

![Extend](readme/03.JPG)

## Structure
- `main.py` - entry + logging setup
- `config.py` - `StreamConfig` TypedDict, `lock`/`stop_event`/`server_lock`, `generate_access_code()`
- `monitor.py` - `get_ip()`, `get_available_monitors()`, `get_monitor_offset()` (dynamic), `init_monitors()`
- `capture.py` - `generate()` (perf_counter, yield multipart)
- `server.py` - Flask `app`, `is_authorized()`, `run_server()`, `/_check_port_available()`
- `gui.py` - `class App(tk.Tk)` (Phase 3), `create_gui()` factory

## Security
- Default `1234` for demo; use **Gen** to create `8-char` `A-Z/2-9` code (`secrets`)
- Code can be sent via `?code=` or header `X-Access-Code` (avoids URL logging)
- Rate-limit: 429 after 10 failed attempts per 60s per IP

## Logging
```bat
python main.py 2> app.log
```
Levels: `INFO` for start/stop, `DEBUG` for frame/cursor details.

## Requirements (pinned)
```
dxcam==0.3.0
Flask==3.0.3
Werkzeug==3.0.3
pywin32==311
numpy==1.26.4
comtypes==1.4.8
Pillow==11.0.0
simplejpeg==1.9.0
```
