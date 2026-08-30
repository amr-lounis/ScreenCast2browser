"""
capture.py - Screen capture and frame generation
"""
import time
import cv2
import config
from monitor import get_monitor_offset

try:
    import win32api
    HAS_WIN32 = config.HAS_WIN32
except ImportError:
    HAS_WIN32 = False
    win32api = None


def generate():
    """Frame generator - runs in Flask thread"""
    while config.is_running:
        cam = config.camera
        frame = cam.get_latest_frame() if cam else None
        if frame is None:
            time.sleep(0.01)
            continue

        frame = frame.copy()
        # dxcam returns RGBA/RGB while cv2.imencode expects BGR
        if len(frame.shape) == 3:
            if frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
            elif frame.shape[2] == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        h, w = frame.shape[0], frame.shape[1]

        show_cur = config.config["show_cursor"]
        quality = config.config["quality"]
        monitor_idx = config.config["monitor_idx"]
        fps = config.config["fps"]

        if show_cur and HAS_WIN32:
            try:
                x, y = win32api.GetCursorPos()
                off_x, off_y = get_monitor_offset(monitor_idx)
                vx = x - off_x
                vy = y - off_y
                if 0 <= vx < w and 0 <= vy < h:
                    cv2.circle(frame, (vx, vy), 8, (0, 255, 0), 2)
                    cv2.drawMarker(frame, (vx, vy), (0, 255, 0), cv2.MARKER_CROSS, 20, 2)
            except Exception:
                pass

        _, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        if not _:
            time.sleep(0.01)
            continue

        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

        if fps > 0:
            time.sleep(1.0 / fps)
