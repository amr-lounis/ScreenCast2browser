"""
config.py - Shared state and settings (Phase 3: Typed & logged)
App: ScreenCast 2 browser (ScreenCast->browser)
"""
import logging
import threading
import secrets
from typing import TypedDict, List, Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    import win32api  # type: ignore
    HAS_WIN32: bool = True
except ImportError:
    HAS_WIN32 = False
    win32api = None  # type: ignore

# --- comtypes: suppress AV on GC after CoUninitialize (dxcam) ---
# dxcam holds IDXGI COM pointers; if GC runs after CoUninitialize,
# comtypes._compointer_base.__del__ raises OSError: access violation 0xFFFFFFFFFFFFFFFF
# This is "Exception ignored" (harmless) but noisy. Make __del__ swallow OSError.
try:
    import comtypes._post_coinit.unknwn as _ct_unknwn  # type: ignore

    _orig_com_del = _ct_unknwn._compointer_base.__del__  # type: ignore

    def _safe_com_del(self):  # type: ignore
        try:
            return _orig_com_del(self)
        except OSError:
            return None
        except Exception:
            return None

    _ct_unknwn._compointer_base.__del__ = _safe_com_del  # type: ignore
except Exception:
    pass

try:
    from werkzeug.serving import make_server  # type: ignore
    HAS_WERKZEUG: bool = True
except ImportError:
    HAS_WERKZEUG = False
    make_server = None  # type: ignore


class StreamConfig(TypedDict):
    fps: int
    quality: int
    show_cursor: bool
    monitor_idx: int
    access_code: str


# Streaming settings (thread-safe snapshot)
config: StreamConfig = {
    "fps": 30,
    "quality": 70,
    "show_cursor": True,
    "monitor_idx": 0,
    "access_code": "1234",
}

# Global state
camera: Any = None
is_running: bool = False
server: Any = None
server_thread: Optional[threading.Thread] = None

# Thread-safety primitives (Phase 1)
lock = threading.RLock()
stop_event = threading.Event()
stop_event.set()  # not running initially
server_lock = threading.Lock()

# Monitor cache
available_monitors: List[Dict[str, Any]] = []
label_to_idx: Dict[str, int] = {}
idx_to_label: Dict[int, str] = {}

# Rate-limit state for auth (ip -> [timestamps])
_rate_limit: Dict[str, List[float]] = {}
_rate_limit_lock = threading.Lock()


def generate_access_code(length: int = 8) -> str:
    """Generate a cryptographically secure random access code."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # avoid 0/O/1/I
    return "".join(secrets.choice(alphabet) for _ in range(length))


def set_running(running: bool) -> None:
    """Thread-safe setter for is_running + stop_event."""
    global is_running
    with lock:
        is_running = bool(running)
        if running:
            stop_event.clear()
            logger.debug("set_running True")
        else:
            stop_event.set()
            logger.debug("set_running False")


def is_running_check() -> bool:
    """Thread-safe check (prefers stop_event)."""
    return not stop_event.is_set()
