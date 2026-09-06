"""Screen capture: producer thread (dxcam -> JPEG) + latest-only consumer."""
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


def _thick_span(c: int, limit: int, half: int = 1) -> tuple:
    """2px-thick centered span around c within [0, limit), edge-adjusted."""
    c0 = max(0, c - half)
    c1 = min(limit, c + half) if limit > 1 else limit
    if c1 - c0 == 1:
        if c0 > 0:
            c0 -= 1
        elif c1 < limit:
            c1 += 1
    return c0, c1


def _draw_cursor_numpy(frame: np.ndarray, vx: int, vy: int) -> None:
    """Draw green cross (20px, thickness 2) + circle ring (r 6..8) in-place."""
    h, w = frame.shape[0], frame.shape[1]
    channels = frame.shape[2] if frame.ndim == 3 else 1
    color = np.array([0, 255, 0, 255] if channels == 4 else [0, 255, 0], dtype=np.uint8)

    y0, y1 = _thick_span(vy, h)
    x0, x1 = max(0, vx - 10), min(w, vx + 10)
    if y0 < y1 and x0 < x1:
        frame[y0:y1, x0:x1] = color

    x0v, x1v = _thick_span(vx, w)
    y0v, y1v = max(0, vy - 10), min(h, vy + 10)
    if y0v < y1v and x0v < x1v:
        frame[y0v:y1v, x0v:x1v] = color

    r_outer, r_inner = 8, 6
    xs, xe = max(0, vx - r_outer - 1), min(w, vx + r_outer + 2)
    ys, ye = max(0, vy - r_outer - 1), min(h, vy + r_outer + 2)
    if xs >= xe or ys >= ye:
        return
    yy, xx = np.ogrid[ys - vy : ye - vy, xs - vx : xe - vx]
    dist2 = xx * xx + yy * yy
    mask = (dist2 <= r_outer * r_outer) & (dist2 >= r_inner * r_inner)
    if np.any(mask):
        frame[ys:ye, xs:xe][mask] = color


def create_camera(monitor_idx: int):
    """Create dxcam capture (BGRA + numpy, leanest). Raises RuntimeError if none."""
    import dxcam  # local import: keeps capture importable without GPU lib

    for kwargs in (
        {"output_idx": monitor_idx, "output_color": "BGRA", "processor_backend": "numpy"},
        {"output_idx": monitor_idx, "output_color": "BGRA"},
        {"output_idx": monitor_idx},
    ):
        try:
            cam = dxcam.create(**kwargs)  # type: ignore
        except TypeError:
            continue  # old dxcam without processor_backend
        if cam is not None:
            return cam
    raise RuntimeError(f"Cannot create capture for monitor {monitor_idx} (not found)")


def _encode_jpeg(frame: np.ndarray, quality: int) -> bytes:
    """Encode frame to JPEG bytes. Tries simplejpeg (fast) then Pillow."""
    quality = int(max(10, min(95, quality)))
    if frame.dtype != np.uint8:
        frame = frame.astype(np.uint8)
    channels = frame.shape[2] if frame.ndim == 3 else 1
    # BGRA direct is the leanest dxcam mode (no conversion); 3ch comes from
    # BGRA so BGR keeps R/B order (if colors ever invert, use "RGB").
    if HAS_SIMPLEJPEG and simplejpeg is not None:
        try:
            colorspace = {4: "BGRA", 3: "BGR"}.get(channels, "GRAY")
            subsampling = "Gray" if colorspace == "GRAY" else "420"
            return simplejpeg.encode_jpeg(
                frame, quality=quality, colorspace=colorspace, colorsubsampling=subsampling, fastdct=True
            )
        except Exception as e:
            logger.debug("simplejpeg encode failed: %s, fallback to Pillow", e)

    if HAS_PIL and Image is not None:
        # Pillow expects RGB: BGRA -> RGB via [2::-1], BGR -> RGB via [::-1]
        if channels == 4:
            rgb = np.ascontiguousarray(frame[:, :, 2::-1])
        elif channels == 3:
            rgb = np.ascontiguousarray(frame[:, :, ::-1])
        else:
            rgb = frame
        im = Image.fromarray(rgb)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality, subsampling=2, optimize=False)
        return buf.getvalue()

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
    # Snapshot settings every N frames to reduce lock contention in hot loop
    fps, quality, show_cur, monitor_idx = config.snapshot_settings()
    source_mode, _window_hwnd = config.snapshot_source()
    tick = 0
    while not config.stop_event.is_set():
        frame_start = time.perf_counter()
        if tick % 30 == 0:
            try:
                fps, quality, show_cur, monitor_idx = config.snapshot_settings()
                source_mode, _window_hwnd = config.snapshot_source()
            except Exception as e:
                logger.debug("config snapshot failed: %s", e)
        tick += 1
        is_window_mode = (source_mode == "window")
        if is_window_mode:
            # Window mode: WGC session owns capture (see window_capture.py).
            # None -> minimized/closed -> freeze last frame (skip publish).
            with config.lock:
                wsession = config.window_session
            if config.stop_event.is_set():
                break
            try:
                raw = wsession.get_latest_frame() if wsession else None  # type: ignore
            except Exception as e:
                logger.debug("window get_latest_frame failed: %s", e)
                raw = None
        else:
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

        # Window mode: WGC draws cursor natively (cursor_capture=True),
        # screen coords don't map to window frame - skip custom overlay.
        if show_cur and not is_window_mode and HAS_WIN32 and win32api is not None:
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
