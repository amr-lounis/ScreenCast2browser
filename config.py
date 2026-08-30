"""
config.py - Shared state and settings
App: ScreenCast 2 browser (ScreenCast->browser)
"""
try:
    import win32api
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    win32api = None

try:
    from werkzeug.serving import make_server
    HAS_WERKZEUG = True
except ImportError:
    HAS_WERKZEUG = False
    make_server = None

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

# Monitor cache
available_monitors = []
label_to_idx = {}
idx_to_label = {}
