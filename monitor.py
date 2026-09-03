"""Monitor and network discovery."""
import gc
import logging
import socket
from typing import List, Dict, Any, Tuple

import dxcam
import config

logger = logging.getLogger(__name__)

# Use centralized HAS_WIN32/win32api from config (Phase 1 unification)
HAS_WIN32: bool = config.HAS_WIN32
win32api = config.win32api


def get_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP: str = s.getsockname()[0]
    except OSError as e:
        logger.debug("get_ip fallback to 127.0.0.1: %s", e)
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP


def get_available_monitors() -> List[Dict[str, Any]]:
    """Detect only physically available monitors"""
    monitors: List[Dict[str, Any]] = []
    if HAS_WIN32:
        try:
            raw = win32api.EnumDisplayMonitors(None, None)  # type: ignore
            for i, h in enumerate(raw):
                info = win32api.GetMonitorInfo(h[0])  # type: ignore
                rc = info['Monitor']  # (left, top, right, bottom)
                w = rc[2] - rc[0]
                hgt = rc[3] - rc[1]
                is_primary = bool(info.get('Flags', 0) & 1)
                dev = info.get('Device', f"DISPLAY{i+1}")
                short_dev = dev.split("\\")[-1] if "\\" in dev else dev
                label = f"{i}: {w}x{hgt} @ ({rc[0]},{rc[1]})" + (" [Primary]" if is_primary else f" [{short_dev}]")
                monitors.append({"idx": i, "label": label, "rect": rc, "primary": is_primary})
            if monitors:
                logger.info("Found %d monitors via Win32", len(monitors))
                return monitors
        except Exception as e:
            logger.debug("Win32 monitor detection failed: %s", e)

    # Fallback: probe via dxcam (BGRA + numpy, leanest)
    for i in range(5):
        c = None
        try:
            try:
                c = dxcam.create(output_idx=i, output_color="BGRA", processor_backend="numpy")
            except TypeError:
                c = dxcam.create(output_idx=i, output_color="BGRA")
            if c is not None:
                monitors.append({"idx": i, "label": f"{i}: Monitor {i}", "rect": None, "primary": i == 0})
        except Exception as e:
            logger.debug("dxcam probe idx %d failed: %s", i, e)
        finally:
            if c is not None:
                _release_probe(c, i)
    if not monitors:
        logger.warning("No monitors detected, using default")
        monitors = [{"idx": 0, "label": "0: Default 1920x1080", "rect": (0, 0, 1920, 1080), "primary": True}]
    else:
        logger.info("Found %d monitors via dxcam fallback", len(monitors))
    return monitors


def _release_probe(c: Any, idx: int) -> None:
    """Stop + explicitly release a dxcam probe before GC (avoids comtypes AV)."""
    try:
        if hasattr(c, "stop"):
            try:
                c.stop()
            except Exception as e:
                logger.debug("dxcam stop failed idx %d: %s", idx, e)
        for meth in ("release", "close"):
            if hasattr(c, meth):
                try:
                    getattr(c, meth)()
                except Exception:
                    pass
                break
    except Exception as e:
        logger.debug("dxcam cleanup failed idx %d: %s", idx, e)
    finally:
        try:
            del c
        except Exception:
            pass
        try:
            gc.collect()
        except Exception:
            pass


def get_monitor_offset(idx: int) -> Tuple[int, int]:
    """Real offset for monitor idx - dynamic fallback, no hardcoded 1920."""
    for m in config.available_monitors:
        if m["idx"] == idx and m["rect"]:
            return m["rect"][0], m["rect"][1]
    if HAS_WIN32 and win32api is not None:
        try:
            monitors = win32api.EnumDisplayMonitors(None, None)  # type: ignore
            if 0 <= idx < len(monitors):
                rc = win32api.GetMonitorInfo(monitors[idx][0])["Monitor"]  # type: ignore
                return rc[0], rc[1]
        except Exception as e:
            logger.debug("get_monitor_offset live query failed idx %d: %s", idx, e)
    rects = [m["rect"] for m in config.available_monitors if m.get("rect")]
    if rects:
        known = sorted(m["idx"] for m in config.available_monitors if m.get("rect"))
        if idx not in known and idx > max(known, default=-1):
            return max(rc[2] for rc in rects), 0
    return 0, 0


def cache_monitors(monitors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Replace monitor cache + lookup maps (single place, used by GUI too)."""
    config.available_monitors[:] = monitors
    config.label_to_idx.clear()
    config.label_to_idx.update({m["label"]: m["idx"] for m in monitors})
    config.idx_to_label.clear()
    config.idx_to_label.update({m["idx"]: m["label"] for m in monitors})
    return monitors


def init_monitors() -> List[Dict[str, Any]]:
    """Refresh monitor cache at startup."""
    monitors = cache_monitors(get_available_monitors())
    if monitors:
        with config.lock:
            config.config["monitor_idx"] = monitors[0]["idx"]
    logger.info("init_monitors: %d monitors cached", len(monitors))
    return monitors
