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

## Comparison vs Alternatives

> Why ScreenCast→browser? **100% open-source, no ads/banners, no paywall, no limits — just browser.**

| Feature | **ScreenCast→browser** ✅ | **Deskreen CE** | **Weylus** | **spacedesk** | **Sunshine + Moonlight** |
|---------|--------------------------|-----------------|------------|---------------|---------------------------|
| **Open Source** | **✅ 100% — full features** | ⚠️ AGPL-3.0 CE only — Pro is closed & paywalled | ✅ AGPL-3.0 — 100% open | ❌ Proprietary — closed source | ✅ **GPL-3.0** both (LizardByte/Sunshine + Moonlight) — 100% open, 40k+ ⭐ |
| **Price / Ads** | **✅ Free forever, zero ads/banners** | ⚠️ Free CE but **Pro upsell** ($24.99/yr for 5 devices, $139/yr Teams) + nag screens | ✅ Free, no ads | ⚠️ Free non-commercial **expires** + **sticky banner** *“spacedesk non-commercial viewer connected”* that can't be closed; commercial license paid per connection | ✅ **Free forever, zero ads** — no subscription, no cloud |
| **Viewer install** | **✅ Nothing — any modern browser** (phone/tablet/TV/PC) | ✅ Browser only | ✅ Browser only (Firefox 80+/iOS 13+ recommended) | ⚠️ **Native app required** for full features; HTML5 viewer is beta/limited | ❌ **Must install Moonlight client** (Android APK / iOS / Windows / Linux / Vita / Switch) — **no browser** |
| **Host OS** | Windows 10/11 (DXGI/dxcam) | ✅ Windows / macOS / Linux (Electron) | ✅ Win/macOS/Linux — **best on Linux** | **Windows host only** (8.1/10/11) | ✅ Windows / Linux / macOS / SteamOS / Docker — any GPU (NVENC/AMF/QuickSync/VAAPI) |
| **True 2nd screen (extend, not just mirror)** | ✅ via [Virtual-Display-Driver](https://github.com/VirtualDrivers/Virtual-Display-Driver) (1 click, select as monitor) | ✅ via Virtual Display Adapter | ⚠️ Complex — `xrandr VirtualHeads` / dummy plug / sway `create_output` (Linux-centric) | ✅ **Built-in** virtual display driver | ⚠️ **Mirror / game-stream only** — 1 active stream per GPU; extend needs virtual display or [Apollo fork](https://github.com/ClassicOldSong/Apollo) |
| **Monitor selection** | **✅ Live Win32 detection + dxcam fallback, dynamic offset** | ✅ Select display / app window | ⚠️ Whole screen only on Win/macOS; window capture Linux only | ✅ Select monitor / extend / duplicate | ✅ Select display / app (`apps.json`, desktop mode) |
| **Video transport** | **MJPEG via Flask (simplejpeg turbo + Pillow)** — zero WebRTC/ffmpeg complexity, works everywhere | WebRTC (Electron) | H.264 + ffmpeg + MSE (Fragmented MP4, hardware accel optional) | Proprietary WDDM driver + network/USB | **H.264 / H.265 / AV1** hardware-encoded (NVENC/AMF/QuickSync), RTSP/GameStream protocol, ultra-low latency |
| **Latency / Quality control** | ✅ **FPS 5–60 + Quality 10–95 sliders**, `perf_counter` pacing, no extra copy | Adaptive quality | Hardware accel but highly variable quality | Low latency + audio | **✅ Best for gaming ~10–20 ms**, bitrate/HDR toggles in Moonlight, needs 5 GHz / Ethernet for 4K |
| **Security** | **✅ Access code (`secrets.compare_digest`) + `X-Access-Code` header + 10/min rate-limit (429)** | ✅ End-to-end encryption (tweetnacl) | ⚠️ Access code only — **explicitly no encryption** (“only trusted networks”) | ❌ No password / no E2E encryption (plain TCP) | ✅ **PIN pairing (4-digit, 30s) + HTTPS Web UI `:47990`** + auto service |
| **Resilience** | **✅ Auto-reconnect** — `abort-previous`, exponential backoff, `naturalWidth` stall detection, `visibilitychange` resume, `Connection: close` | Basic reconnect | Manual refresh | Driver-level reconnect | ✅ Auto-discovery + PIN re-pair, 1 viewer at a time |
| **Footprint / Setup** | **✅ ~77 MB single EXE**, `pip install` → run | ❌ ~140 MB Electron | ✅ ~20 MB Rust (complex build) | Driver + service install | ⚠️ **Heavy** — Sunshine service + GPU drivers + Moonlight on every device + firewall ports `47984-47990` |
| **Audio / Touch / Pen / Gamepad** | ❌ Pure display — KVM via OS | Mirror only | **✅ Stylus pressure/tilt + multi-touch** (Linux uinput) | **✅ Touch / pen / keyboard / audio** | **✅ Gamepad + rumble + mouse/kb + audio + HDR** — built for gaming |
| **Best for** | **Lightweight mirroring / extending to any browser, no limits, no ads** | Easy second screen if you accept CE limits / Pro price | **Linux artists** wanting tablet as graphic tablet | Windows users wanting built-in extend + touch/audio | **Gamers** wanting low-latency game streaming to Deck/TV/phone — **overkill for office docs** |

*Deskreen CE = [pavlobu/deskreen](https://github.com/pavlobu/deskreen) AGPL-3.0, CE has “limited features. If you need more please upgrade to Pro” — see README. Spacedesk free = “expiry date in Driver Console + banner” per [licensing](https://www.spacedesk.net/licensing/) and [forum](https://www.spacedesk.net/support-forum/topic/non-commercial-paid-user-license/). Weylus = “Please only run in networks you trust as there is no encryption” per README. Sunshine = [LizardByte/Sunshine](https://github.com/LizardByte/Sunshine) (40k+ ⭐) + Moonlight — PIN pairing via `https://localhost:47990`, needs Moonlight client on every device, 1 active stream/GPU, ideal for gaming not office extend.*

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
comtypes==1.4.12
Pillow==11.0.0
simplejpeg==1.9.0
```
