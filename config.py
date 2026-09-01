"""
config.py - Shared state and settings
App: ScreenCast 2 browser (ScreenCast->browser)
"""
import threading
import secrets

try:
    import win32api  # type: ignore
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    win32api = None  # type: ignore

try:
    from werkzeug.serving import make_server  # type: ignore
    HAS_WERKZEUG = True
except ImportError:
    HAS_WERKZEUG = False
    make_server = None  # type: ignore

# Streaming settings (thread-safe snapshot)
config = {
    "fps": 30,
    "quality": 70,
    "show_cursor": True,
    "monitor_idx": 0,
    "access_code": "1234",
}

# Global state
camera = None
is_running = False
server = None
server_thread = None

# Thread-safety primitives (Phase 1)
lock = threading.RLock()
stop_event = threading.Event()
stop_event.set()  # not running initially
server_lock = threading.Lock()

# Monitor cache
available_monitors = []
label_to_idx = {}
idx_to_label = {}

# Rate-limit state for auth (ip -> [timestamps])
_rate_limit = {}
_rate_limit_lock = threading.Lock()


def generate_access_code(length: int = 8) -> str:
    """Generate a cryptographically secure random access code."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # avoid 0/O/1/I
    return "".join(secrets.choice(alphabet) for _ in range(length))


def set_running(running: bool):
    """Thread-safe setter for is_running + stop_event."""
    global is_running
    with lock:
        is_running = bool(running)
        if running:
            stop_event.clear()
        else:
            stop_event.set()


def is_running_check() -> bool:
    """Thread-safe check (prefers stop_event)."""
    return not stop_event.is_set()
