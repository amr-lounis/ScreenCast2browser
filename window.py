"""Window discovery for app-window capture (isolated module).

This module only enumerates top-level windows via Win32.
Actual frame capture lives in window_capture.py (WGC backend).
Monitor logic in monitor.py is untouched.
"""
import logging
from typing import List, Dict, Any, Optional, Tuple

import config

logger = logging.getLogger(__name__)

HAS_WIN32GUI: bool = False
win32gui: Any = None
try:
    import win32gui as _wg  # type: ignore
    win32gui = _wg
    HAS_WIN32GUI = True
except ImportError:
    HAS_WIN32GUI = False

# Minimum client area to filter out tooltips/trays/menus
_MIN_W: int = 120
_MIN_H: int = 80

# Substrings (lowercase) to skip - helper/host windows without useful content
_SKIP_TITLES = (
    "program manager",
    "microsoft text input application",
    "windows input experience",
    "settings",  # Win11 Settings host often duplicates; keep real apps
)


def _is_capturable(hwnd: int) -> Optional[Dict[str, Any]]:
    """Return window info dict if capturable, else None."""
    if not HAS_WIN32GUI or win32gui is None:
        return None
    try:
        if not win32gui.IsWindowVisible(hwnd):
            return None
        title = (win32gui.GetWindowText(hwnd) or "").strip()
        if not title:
            return None
        # Skip minimized (iconic) - no content to capture
        try:
            if win32gui.IsIconic(hwnd):
                return None
        except Exception:
            pass
        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        except Exception:
            return None
        w, h = right - left, bottom - top
        if w < _MIN_W or h < _MIN_H:
            return None
        low = title.lower()
        # Exact skip only for known host windows; keep everything else
        if low in ("program manager", "microsoft text input application"):
            return None
        return {"hwnd": int(hwnd), "title": title, "rect": (left, top, right, bottom),
                "w": w, "h": h}
    except Exception as e:
        logger.debug("window probe failed hwnd=%s: %s", hwnd, e)
        return None


def get_available_windows() -> List[Dict[str, Any]]:
    """Enumerate capturable top-level windows, sorted by title."""
    windows: List[Dict[str, Any]] = []
    if not HAS_WIN32GUI or win32gui is None:
        logger.warning("win32gui not available - window list empty")
        return windows
    try:
        hwns: List[int] = []
        win32gui.EnumWindows(lambda h, p: p.append(h), hwns)
    except Exception as e:
        logger.debug("EnumWindows failed: %s", e)
        return windows
    for h in hwns:
        info = _is_capturable(h)
        if info is not None:
            # label shows title + size; hwnd is the stable key
            info["label"] = f'{info["title"][:60]} ({info["w"]}x{info["h"]})'
            windows.append(info)
    windows.sort(key=lambda m: m["title"].lower())
    logger.info("Found %d capturable windows", len(windows))
    return windows


def cache_windows(windows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Replace window cache + lookup maps (mirrors monitor.cache_monitors)."""
    config.available_windows[:] = windows
    config.hwnd_to_label.clear()
    config.label_to_hwnd.clear()
    for w in windows:
        config.hwnd_to_label[int(w["hwnd"])] = w["label"]
        config.label_to_hwnd[w["label"]] = int(w["hwnd"])
    return windows


def init_windows() -> List[Dict[str, Any]]:
    """Refresh window cache at startup (non-fatal if empty)."""
    windows = cache_windows(get_available_windows())
    # Default to first window if no hwnd selected yet
    if windows:
        with config.lock:
            if int(config.config.get("window_hwnd", 0) or 0) == 0:
                config.config["window_hwnd"] = int(windows[0]["hwnd"])
                config.config["window_title"] = str(windows[0]["title"])
    return windows


def is_window_valid(hwnd: int) -> bool:
    """True if hwnd still exists and is visible (not closed)."""
    if not HAS_WIN32GUI or win32gui is None or not hwnd:
        return False
    try:
        return bool(win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd))
    except Exception:
        return False


def is_window_minimized(hwnd: int) -> bool:
    """True if window is minimized (iconic) - caller should freeze last frame."""
    if not HAS_WIN32GUI or win32gui is None or not hwnd:
        return False
    try:
        return bool(win32gui.IsIconic(hwnd))
    except Exception:
        return False


def get_window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """Current window rect or None if unavailable."""
    if not HAS_WIN32GUI or win32gui is None or not hwnd:
        return None
    try:
        return tuple(win32gui.GetWindowRect(hwnd))  # type: ignore
    except Exception:
        return None
