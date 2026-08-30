# ScreenCast->browser

ScreenCast 2 browser — stream desktop to any device browser on the same network, no install needed. Captures via DXGI (dxcam) and streams MJPEG via Flask, with monitor selection, FPS/quality control, access code protection and auto-reconnect on disconnect.

![GUI](readme/01.JPG)

## Run
```bat
pip install -r requirements.txt
python main.py
```
Open `http://IP:PORT/?code=1234` (default code `1234`)

![Browser](readme/02.JPG)

## Build EXE
```bat
build.bat
```
Output: `dist/ScreenCast-browser.exe`

## Tip: Extend Display to Any Browser Device
Use https://github.com/VirtualDrivers/Virtual-Display-Driver to create a virtual monitor, then select it in ScreenCast->browser to extend your desktop to any device with a web browser (phone, tablet, TV).

![Extend](readme/03.JPG)

## Structure
`main.py` `config.py` `monitor.py` `capture.py` `server.py` `gui.py`
