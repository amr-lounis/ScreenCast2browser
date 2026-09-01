"""
capture.py - Screen capture and frame generation
"""
import time
import cv2
import config
from monitor import get_monitor_offset

# Centralized HAS_WIN32/win32api (Phase 1)
HAS_WIN32 = config.HAS_WIN32
win32api = config.win32api


def generate():
    """Frame generator - runs in Flask thread"""
    while not config.stop_event.is_set():
        # Thread-safe camera read
        with config.lock:
            cam = config.camera
        # Also check legacy is_running for compatibility
        if config.stop_event.is_set():
            break
        try:
            frame = cam.get_latest_frame() if cam else None
        except Exception:
            frame = None
        if frame is None:
            # wait respectfully, but abort quickly if stopping
            if config.stop_event.wait(0.01):
                break
            continue

        frame = frame.copy()
        # dxcam returns RGBA/RGB while cv2.imencode expects BGR
        if len(frame.shape) == 3:
            if frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
            elif frame.shape[2] == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        h, w = frame.shape[0], frame.shape[1]

        # Snapshot config under lock to avoid torn reads
        with config.lock:
            show_cur = config.config["show_cursor"]
            quality = config.config["quality"]
            monitor_idx = config.config["monitor_idx"]
            fps = config.config["fps"]

        if show_cur and HAS_WIN32 and win32api is not None:
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

        try:
            ok, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        except Exception:
            ok, jpeg = False, None
        if not ok or jpeg is None:
            if config.stop_event.wait(0.01):
                break
            continue

        try:
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        except (GeneratorExit, BrokenPipeError, ConnectionAbortedError, OSError):
            # Client disconnected
            break
        except Exception:
            break

        if fps > 0:
            if config.stop_event.wait(1.0 / fps):
                break
