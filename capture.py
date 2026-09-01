"""
capture.py - Screen capture and frame generation (Phase 3: typed & logged)
"""
import logging
import time
from typing import Generator

import cv2
import config
from monitor import get_monitor_offset

logger = logging.getLogger(__name__)

# Centralized HAS_WIN32/win32api (Phase 1)
HAS_WIN32: bool = config.HAS_WIN32
win32api = config.win32api


def generate() -> Generator[bytes, None, None]:
    """Frame generator - runs in Flask thread (Phase 2: perf_counter + no extra copy)"""
    logger.info("generate started")
    while not config.stop_event.is_set():
        frame_start = time.perf_counter()
        with config.lock:
            cam = config.camera
        if config.stop_event.is_set():
            break
        try:
            frame = cam.get_latest_frame() if cam else None  # type: ignore
        except Exception as e:
            logger.debug("get_latest_frame failed: %s", e)
            frame = None
        if frame is None:
            if config.stop_event.wait(0.01):
                break
            continue

        try:
            if len(frame.shape) == 3:
                if frame.shape[2] == 4:
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
                elif frame.shape[2] == 3:
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            h, w = frame.shape[0], frame.shape[1]
        except Exception as e:
            logger.debug("frame shape handling failed: %s", e)
            if config.stop_event.wait(0.01):
                break
            continue

        with config.lock:
            show_cur = config.config["show_cursor"]
            quality = config.config["quality"]
            monitor_idx = config.config["monitor_idx"]
            fps = config.config["fps"]

        if show_cur and HAS_WIN32 and win32api is not None:
            try:
                x, y = win32api.GetCursorPos()  # type: ignore
                off_x, off_y = get_monitor_offset(monitor_idx)
                vx = x - off_x
                vy = y - off_y
                if 0 <= vx < w and 0 <= vy < h:
                    cv2.circle(frame, (vx, vy), 8, (0, 255, 0), 2)
                    cv2.drawMarker(frame, (vx, vy), (0, 255, 0), cv2.MARKER_CROSS, 20, 2)
            except Exception as e:
                logger.debug("cursor draw failed: %s", e)

        try:
            ok, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        except Exception as e:
            logger.debug("imencode failed: %s", e)
            ok, jpeg = False, None
        if not ok or jpeg is None:
            if config.stop_event.wait(0.01):
                break
            continue

        try:
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        except (GeneratorExit, BrokenPipeError, ConnectionAbortedError, OSError) as e:
            logger.info("client disconnected: %s", e)
            break
        except Exception as e:
            logger.exception("generate yield failed: %s", e)
            break

        if fps > 0:
            elapsed = time.perf_counter() - frame_start
            sleep_time = (1.0 / fps) - elapsed
            if sleep_time > 0:
                if config.stop_event.wait(sleep_time):
                    break
    logger.info("generate stopped")
