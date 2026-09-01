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
    """Frame generator - runs in Flask thread (Phase 2: perf_counter + no extra copy)"""
    while not config.stop_event.is_set():
        frame_start = time.perf_counter()
        # Thread-safe camera read
        with config.lock:
            cam = config.camera
        if config.stop_event.is_set():
            break
        try:
            frame = cam.get_latest_frame() if cam else None
        except Exception:
            frame = None
        if frame is None:
            if config.stop_event.wait(0.01):
                break
            continue

        # dxcam returns RGBA/RGB while cv2.imencode expects BGR
        # Avoid extra frame.copy() - cv2.cvtColor creates a new buffer anyway
        # Only copy if we need to draw cursor without conversion path? Handled below.
        try:
            if len(frame.shape) == 3:
                if frame.shape[2] == 4:
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
                elif frame.shape[2] == 3:
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                # else: keep as is (e.g., BGR already)
            # For 2D grayscale, keep as is
            h, w = frame.shape[0], frame.shape[1]
        except Exception:
            # Invalid frame shape
            if config.stop_event.wait(0.01):
                break
            continue

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
                    # Draw directly on BGR frame (already converted)
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
            break
        except Exception:
            break

        if fps > 0:
            elapsed = time.perf_counter() - frame_start
            sleep_time = (1.0 / fps) - elapsed
            if sleep_time > 0:
                if config.stop_event.wait(sleep_time):
                    break
            # else: we're behind schedule, yield next frame immediately (no sleep)
