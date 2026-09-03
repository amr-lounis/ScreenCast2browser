"""
capture.py - Screen capture and frame generation
Uses simplejpeg (libjpeg-turbo) for fast JPEG, Pillow as fallback, numpy for cursor.
BGRA is the leanest dxcam path - direct simplejpeg encoding without conversion.
"""
import io
import logging
import time
from typing import Generator

import numpy as np

import config
from monitor import get_monitor_offset

logger = logging.getLogger(__name__)

# Centralized HAS_WIN32/win32api (Phase 1)
HAS_WIN32: bool = config.HAS_WIN32
win32api = config.win32api

try:
    import simplejpeg  # type: ignore

    HAS_SIMPLEJPEG: bool = True
except ImportError:
    HAS_SIMPLEJPEG = False
    simplejpeg = None  # type: ignore

try:
    from PIL import Image  # type: ignore

    HAS_PIL: bool = True
except ImportError:
    HAS_PIL = False
    Image = None  # type: ignore


def _draw_cursor_numpy(frame: np.ndarray, vx: int, vy: int) -> None:
    """Draw green cross + circle (r=8, thickness=2) directly on frame (BGR/BGRA).

    Modifies frame in-place. Works for both 3-channel BGR/RGB and 4-channel BGRA/RGBA.
    Color is green (0,255,0) in BGR - same for RGB (0,255,0) is also green.
    """
    h, w = frame.shape[0], frame.shape[1]
    channels = frame.shape[2] if frame.ndim == 3 else 1
    # green in BGR and RGB is same (0,255,0)
    # For BGRA we keep alpha 255
    if channels == 4:
        color = np.array([0, 255, 0, 255], dtype=np.uint8)
    else:
        color = np.array([0, 255, 0], dtype=np.uint8)

    # --- cross: horizontal 20px, vertical 20px, thickness 2 ---
    # horizontal
    y0 = max(0, vy - 1)
    y1 = min(h, vy + 1) if h > 1 else h  # thickness 2: vy-1 to vy+1
    # adjust to exactly 2px when possible
    if y1 - y0 == 1 and y0 > 0:
        y0 -= 1
    elif y1 - y0 == 1 and y1 < h:
        y1 += 1
    x0 = max(0, vx - 10)
    x1 = min(w, vx + 10)
    if y0 < y1 and x0 < x1:
        frame[y0:y1, x0:x1] = color

    # vertical
    x0v = max(0, vx - 1)
    x1v = min(w, vx + 1)
    if x1v - x0v == 1 and x0v > 0:
        x0v -= 1
    elif x1v - x0v == 1 and x1v < w:
        x1v += 1
    y0v = max(0, vy - 10)
    y1v = min(h, vy + 10)
    if y0v < y1v and x0v < x1v:
        frame[y0v:y1v, x0v:x1v] = color

    # --- circle ring r=8 thickness 2 (6..8) ---
    r_outer = 8
    r_inner = 6
    x_start = max(0, vx - r_outer - 1)
    x_end = min(w, vx + r_outer + 2)
    y_start = max(0, vy - r_outer - 1)
    y_end = min(h, vy + r_outer + 2)
    if x_start >= x_end or y_start >= y_end:
        return
    # vectorized ring mask
    yy, xx = np.ogrid[y_start - vy : y_end - vy, x_start - vx : x_end - vx]
    dist2 = xx * xx + yy * yy
    mask = (dist2 <= r_outer * r_outer) & (dist2 >= r_inner * r_inner)
    if np.any(mask):
        # apply only where mask true
        region = frame[y_start:y_end, x_start:x_end]
        # region[mask] works for (h,w,3) -> need broadcasting
        region[mask] = color


def _encode_jpeg(frame: np.ndarray, quality: int) -> bytes:
    """Encode frame to JPEG bytes. Tries simplejpeg (fast) then Pillow."""
    quality = int(max(10, min(95, quality)))
    h, w = frame.shape[0], frame.shape[1]
    # Ensure uint8 contiguous
    if frame.dtype != np.uint8:
        frame = frame.astype(np.uint8)
    # simplejpeg path - fastest, supports BGRA/BGR directly without copy
    if HAS_SIMPLEJPEG and simplejpeg is not None:
        try:
            if frame.ndim == 3 and frame.shape[2] == 4:
                # BGRA direct - no numpy conversion (leanest dxcam mode)
                # colorsubsampling='420' is smallest/fastest (4:2:0 chroma subsampling)
                return simplejpeg.encode_jpeg(
                    frame, quality=quality, colorspace="BGRA", colorsubsampling="420", fastdct=True
                )
            elif frame.ndim == 3 and frame.shape[2] == 3:
                # 3-channel: dxcam default was RGB, but BGRA mode gives 4ch
                # Treat as BGR (if BGRA sliced) vs RGB (default). Since we request BGRA, this is fallback.
                # Use BGR (BGRA sliced). If colors inverted, change to "RGB".
                # We try BGR first; it's zero-copy if frame is already BGR contiguous.
                # For RGB input, BGR will invert R/B - user can toggle by changing colorspace.
                return simplejpeg.encode_jpeg(
                    frame, quality=quality, colorspace="BGR", colorsubsampling="420", fastdct=True
                )
            else:
                # Gray
                return simplejpeg.encode_jpeg(
                    frame, quality=quality, colorspace="GRAY", colorsubsampling="Gray", fastdct=True
                )
        except Exception as e:
            logger.debug("simplejpeg encode failed: %s, fallback to Pillow", e)

    if HAS_PIL and Image is not None:
        try:
            # Pillow expects RGB
            if frame.ndim == 3 and frame.shape[2] == 4:
                # BGRA -> RGB: [B,G,R,A] -> [R,G,B] via 2::-1 slice (R,G,B)
                # frame[:,:,2::-1] gives (R,G,B) with negative stride -> need contiguous copy
                rgb = np.ascontiguousarray(frame[:, :, 2::-1])
            elif frame.ndim == 3 and frame.shape[2] == 3:
                # Assume BGR (from BGRA) -> RGB, so flip. If frame is already RGB, this will invert;
                # but BGRA path is primary, so flip is correct.
                # We treat 3ch as BGR (BGRA primary path).
                rgb = np.ascontiguousarray(frame[:, :, ::-1])
            else:
                rgb = frame
            # Pillow subsampling: 0=444, 1=422, 2=420 (2 is smallest/fastest, matches simplejpeg 420)
            im = Image.fromarray(rgb)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=quality, subsampling=2, optimize=False)
            return buf.getvalue()
        except Exception as e:
            logger.debug("Pillow encode failed: %s", e)
            raise

    raise RuntimeError("No JPEG encoder available (install simplejpeg or Pillow)")


def producer_loop() -> None:
    """Single producer: capture + encode + publish latest JPEG (sole pacer).

    Runs in a dedicated background thread. Decouples capture/encode from
    network backpressure so a slow client never stalls capture.
    """
    logger.info("producer started (simplejpeg=%s, PIL=%s)", HAS_SIMPLEJPEG, HAS_PIL)
    if not HAS_SIMPLEJPEG and not HAS_PIL:
        logger.error("No encoder available - install simplejpeg or Pillow")
        return
    # Snapshot config every N frames to reduce lock contention in hot loop
    show_cur = True
    quality = 70
    monitor_idx = 0
    fps = 30
    tick = 0
    with config.lock:
        try:
            show_cur = bool(config.config["show_cursor"])
            quality = int(config.config["quality"])
            monitor_idx = int(config.config["monitor_idx"])
            fps = int(config.config["fps"])
        except Exception:
            pass
    while not config.stop_event.is_set():
        frame_start = time.perf_counter()
        if tick % 30 == 0:
            with config.lock:
                try:
                    show_cur = bool(config.config["show_cursor"])
                    quality = int(config.config["quality"])
                    monitor_idx = int(config.config["monitor_idx"])
                    fps = int(config.config["fps"])
                except Exception as e:
                    logger.debug("config snapshot failed: %s", e)
        tick += 1
        with config.lock:
            cam = config.camera
        if config.stop_event.is_set():
            break
        try:
            raw = cam.get_latest_frame() if cam else None  # type: ignore
        except Exception as e:
            logger.debug("get_latest_frame failed: %s", e)
            raw = None
        if raw is None:
            if config.stop_event.wait(0.01):
                break
            continue
        try:
            if raw.ndim != 3 or raw.shape[2] not in (3, 4):
                logger.debug("unexpected frame shape %s", getattr(raw, "shape", None))
                if config.stop_event.wait(0.01):
                    break
                continue
            # Copy immediately: dxcam reuses its buffer, drawing/encoding
            # on the shared buffer causes tearing.
            frame = raw.copy()
            h, w = frame.shape[0], frame.shape[1]
        except Exception as e:
            logger.debug("frame copy failed: %s", e)
            if config.stop_event.wait(0.01):
                break
            continue

        if show_cur and HAS_WIN32 and win32api is not None:
            try:
                x, y = win32api.GetCursorPos()  # type: ignore
                off_x, off_y = get_monitor_offset(monitor_idx)
                vx = x - off_x
                vy = y - off_y
                if 0 <= vx < w and 0 <= vy < h:
                    _draw_cursor_numpy(frame, vx, vy)
            except Exception as e:
                logger.debug("cursor draw failed: %s", e)

        try:
            jpeg_bytes = _encode_jpeg(frame, quality)
        except Exception as e:
            logger.debug("encode failed: %s", e)
            if config.stop_event.wait(0.01):
                break
            continue

        with config.frame_cond:
            config.latest_jpeg = jpeg_bytes
            config.frame_id += 1
            config.frame_ts = time.time()
            config.frame_cond.notify_all()

        if fps > 0:
            elapsed = time.perf_counter() - frame_start
            sleep_time = (1.0 / fps) - elapsed
            if sleep_time > 0:
                if config.stop_event.wait(sleep_time):
                    break
    logger.info("producer stopped")


def generate() -> Generator[bytes, None, None]:
    """Frame consumer - runs in Flask thread, yields latest-only (drops late).

    Waits on frame_cond for a newer frame_id; never re-sends duplicates and
    never paces itself (producer is the sole pacer), so backpressure from a
    slow client cannot stall capture.
    """
    logger.info("generate subscribed")
    last_sent = -1
    with config.frame_cond:
        last_sent = int(config.frame_id)
    while not config.stop_event.is_set():
        with config.frame_cond:
            while int(config.frame_id) <= last_sent and not config.stop_event.is_set():
                config.frame_cond.wait(timeout=2.0)
            if config.stop_event.is_set():
                break
            last_sent = int(config.frame_id)
            jpeg_bytes = config.latest_jpeg
        if not jpeg_bytes:
            continue
        try:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg_bytes + b"\r\n")
        except (GeneratorExit, BrokenPipeError, ConnectionAbortedError, OSError) as e:
            logger.info("client disconnected: %s", e)
            break
        except Exception as e:
            logger.exception("generate yield failed: %s", e)
            break
    logger.info("generate stopped")
