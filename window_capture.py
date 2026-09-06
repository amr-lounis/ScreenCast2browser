"""App-window capture via Windows Graphics Capture (isolated module).

Primary backend: windows-capture (Rust, WGC) with window_hwnd.
Fallback point: wincam (HWND) - see create_window_session() docstring.

Design notes (kept isolated from monitor_capture.py monitor path):
- Event-based WGC -> latest-only queue (size 1), so producer_loop polls
  without blocking and freezes last frame on minimize/close.
- Frame buffer from WGC is a zero-copy view: copied immediately in callback.
- cursor_capture=True lets WGC draw the cursor natively; monitor_capture.py must
  skip its custom green-crosshair overlay in window mode (coords differ).
- draw_border is left as default (None): forcing False raises on some
  platforms ("Toggling the capture border is not supported").
- on_closed sets closed_event so producer can log + freeze instead of
  spinning on an empty queue.
"""
import logging
import queue
import threading
from typing import Any, Optional

import numpy as np

import config
from window import is_window_minimized, is_window_valid

logger = logging.getLogger(__name__)

try:
    from windows_capture import WindowsCapture as _WGCapture  # type: ignore
    HAS_WGC: bool = True
except ImportError:
    HAS_WGC = False
    _WGCapture = None  # type: ignore

# wincam fallback: optional, only probed if windows-capture missing.
# Kept as extension point (spike succeeded with windows-capture, so not required).
try:
    import wincam  # type: ignore
    HAS_WINCAM: bool = True
except ImportError:
    HAS_WINCAM = False


class WindowCaptureSession:
    """Latest-only WGC session for a single HWND."""

    def __init__(self, hwnd: int, show_cursor: bool = True) -> None:
        self.hwnd: int = int(hwnd)
        self.show_cursor: bool = bool(show_cursor)
        self._q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=1)
        self._capture: Any = None
        self._control: Any = None
        self.closed_event = threading.Event()
        self.frames_received: int = 0

    # --- lifecycle ---
    def start(self) -> None:
        if not HAS_WGC or _WGCapture is None:
            raise RuntimeError(
                "windows-capture not installed (pip install windows-capture). "
                + ("wincam fallback available." if HAS_WINCAM else "No fallback available.")
            )
        if not is_window_valid(self.hwnd):
            raise RuntimeError(f"Window hwnd={self.hwnd} not found or hidden")
        if is_window_minimized(self.hwnd):
            raise RuntimeError("Window is minimized - restore it before starting")
        cap = _WGCapture(cursor_capture=self.show_cursor, window_hwnd=self.hwnd)
        session = self  # closure alias

        @cap.event
        def on_frame_arrived(frame: Any, controller: Any) -> None:  # type: ignore
            try:
                arr = frame.frame_buffer.copy()  # zero-copy view -> own it now
                session.frames_received += 1
                try:
                    session._q.put_nowait(arr)
                except queue.Full:
                    try:
                        session._q.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        session._q.put_nowait(arr)
                    except queue.Full:
                        pass
            except Exception as e:
                logger.debug("WGC frame copy failed: %s", e)

        @cap.event
        def on_closed() -> None:  # type: ignore
            session.closed_event.set()
            logger.info("WGC session closed (hwnd=%s)", session.hwnd)

        self._capture = cap
        # start_free_threaded runs capture on its own thread; callbacks fire there.
        self._control = cap.start_free_threaded()
        with config.lock:
            config.window_session = self
        logger.info("Window capture started hwnd=%s cursor=%s", self.hwnd, self.show_cursor)

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Non-blocking drain of queue; None when minimized/closed/empty.

        Returns None (freeze signal) instead of raising, so producer_loop
        keeps publishing the previous JPEG.
        """
        if self.closed_event.is_set():
            return None
        if is_window_minimized(self.hwnd) or not is_window_valid(self.hwnd):
            return None
        try:
            latest: Optional[np.ndarray] = None
            while True:
                try:
                    latest = self._q.get_nowait()
                except queue.Empty:
                    break
            return latest
        except Exception as e:
            logger.debug("WGC drain failed: %s", e)
            return None

    def stop(self) -> None:
        ctrl, self._control = self._control, None
        if ctrl is not None:
            try:
                ctrl.stop()
            except Exception as e:
                logger.debug("WGC stop error: %s", e)
        with config.lock:
            if config.window_session is self:
                config.window_session = None
        # Drain queue so a stale frame is never replayed after restart
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass
        logger.info("Window capture stopped hwnd=%s frames=%d", self.hwnd, self.frames_received)


def create_window_session(hwnd: int, show_cursor: bool = True) -> WindowCaptureSession:
    """Factory (mirrors monitor_capture.create_camera). Raises RuntimeError if unusable."""
    return WindowCaptureSession(hwnd, show_cursor)


def stop_window_session(session: Optional[WindowCaptureSession] = None) -> None:
    """Stop given session or the global one (safe no-op when None)."""
    sess = session
    if sess is None:
        with config.lock:
            sess = config.window_session
    if sess is not None:
        try:
            sess.stop()
        except Exception as e:
            logger.debug("stop_window_session error: %s", e)
