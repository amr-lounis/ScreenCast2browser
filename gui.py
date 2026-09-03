"""Tkinter control panel."""
import gc
import logging
import threading
import time
import tkinter as tk
from tkinter import ttk
import webbrowser
from typing import List, Dict, Any, Optional

import config
from capture import create_camera, producer_loop
from monitor import cache_monitors, get_available_monitors, get_ip, init_monitors
from server import run_server, _check_port_available

logger = logging.getLogger(__name__)


def _release_cam(cam: Any) -> None:
    """Stop + explicitly release a camera (avoids comtypes AV on GC)."""
    if cam is None:
        return
    try:
        cam.stop()
    except Exception as e:
        logger.debug("Camera stop error: %s", e)
    for meth in ("release", "close"):
        if hasattr(cam, meth):
            try:
                getattr(cam, meth)()
            except Exception:
                pass
            break
    with config.lock:
        if config.camera is cam:
            config.camera = None
    try:
        gc.collect()
    except Exception:
        pass


class App(tk.Tk):
    """Main application window - Phase 3 refactor from monolithic create_gui()."""

    def __init__(self) -> None:
        super().__init__()
        self.title("ScreenCast->browser")
        self.geometry("420x580")
        self.resizable(False, False)

        monitors = init_monitors()
        if not monitors:
            monitors = config.available_monitors
        self.monitors: List[Dict[str, Any]] = monitors

        self._init_vars()
        self._create_widgets()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        logger.info("GUI initialized with %d monitor(s)", len(self.monitors))

    # --- Variables ---
    def _init_vars(self) -> None:
        initial_label = self.monitors[0]["label"] if self.monitors else "0: Default"
        self.monitor_label_var = tk.StringVar(value=initial_label)
        self.fps_var = tk.IntVar(value=config.config["fps"])
        self.quality_var = tk.IntVar(value=config.config["quality"])
        self.port_var = tk.StringVar(value="8080")
        self.show_cursor = tk.BooleanVar(value=config.config["show_cursor"])
        _initial_code: str = config.config.get("access_code", "")
        self.access_code_var = tk.StringVar(value=_initial_code)
        self.link_var = tk.StringVar(value="Server stopped")
        self._url = ""  # raw URL behind link_var display text

    # --- Widgets ---
    def _create_widgets(self) -> None:
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Display Settings", font=('Arial', 13, 'bold')).pack(pady=(0, 15))

        # Monitor row
        row1 = ttk.Frame(main_frame)
        row1.pack(fill=tk.X, pady=5)
        ttk.Label(row1, text="Monitor:").pack(side=tk.LEFT)
        self.monitor_combo = ttk.Combobox(
            row1, textvariable=self.monitor_label_var,
            values=[m["label"] for m in self.monitors], width=26, state="readonly"
        )
        refresh_btn = ttk.Button(row1, text="↻", width=3, command=self._refresh_monitors)
        refresh_btn.pack(side=tk.RIGHT, padx=(5, 0))
        self.monitor_combo.pack(side=tk.RIGHT, padx=(0, 5))

        # FPS row
        row2 = ttk.Frame(main_frame)
        row2.pack(fill=tk.X, pady=5)
        ttk.Label(row2, text="FPS:").pack(side=tk.LEFT)
        self.fps_label = ttk.Label(row2, text=str(config.config["fps"]))
        self.fps_label.pack(side=tk.RIGHT, padx=(10, 0))
        fps_scale = ttk.Scale(row2, from_=5, to=60, variable=self.fps_var, orient=tk.HORIZONTAL, length=130)
        fps_scale.pack(side=tk.RIGHT)
        self.fps_var.trace_add("write", lambda *a: self._on_slider(self.fps_var, self.fps_label, "fps"))

        # Quality row
        row3 = ttk.Frame(main_frame)
        row3.pack(fill=tk.X, pady=5)
        ttk.Label(row3, text="Quality:").pack(side=tk.LEFT)
        self.quality_label = ttk.Label(row3, text=str(config.config["quality"]))
        self.quality_label.pack(side=tk.RIGHT, padx=(10, 0))
        quality_scale = ttk.Scale(row3, from_=10, to=95, variable=self.quality_var, orient=tk.HORIZONTAL, length=130)
        quality_scale.pack(side=tk.RIGHT)
        self.quality_var.trace_add("write", lambda *a: self._on_slider(self.quality_var, self.quality_label, "quality"))

        self.show_cursor.trace_add("write", self._on_cursor_toggle)
        self.monitor_label_var.trace_add("write", self._on_monitor_change)

        ttk.Checkbutton(main_frame, text="Show Cursor", variable=self.show_cursor).pack(anchor=tk.W, pady=10)

        # Port
        row4 = ttk.Frame(main_frame)
        row4.pack(fill=tk.X, pady=5)
        ttk.Label(row4, text="Port:").pack(side=tk.LEFT)
        ttk.Entry(row4, textvariable=self.port_var, width=12).pack(side=tk.RIGHT)

        # Access Code
        row5 = ttk.Frame(main_frame)
        row5.pack(fill=tk.X, pady=5)
        ttk.Label(row5, text="Access Code:").pack(side=tk.LEFT)
        self.access_entry = ttk.Entry(row5, textvariable=self.access_code_var, width=12, show="*")
        self.access_entry.pack(side=tk.RIGHT)

        self.toggle_btn = ttk.Button(row5, text="Show", width=6, command=self._toggle_code)
        self.toggle_btn.pack(side=tk.RIGHT, padx=(5, 0))

        gen_btn = ttk.Button(row5, text="Gen", width=5, command=self._generate_code)
        gen_btn.pack(side=tk.RIGHT, padx=(3, 0))
        ttk.Label(main_frame, text="Empty = no protection", font=('Arial', 7), foreground="gray").pack(anchor=tk.W)

        self.access_code_var.trace_add("write", self._on_access_code_change)

        ttk.Separator(main_frame).pack(fill=tk.X, pady=15)

        # Link row
        link_frame = ttk.Frame(main_frame)
        link_frame.pack(fill=tk.X, pady=10)
        self.link_label = ttk.Label(
            link_frame, textvariable=self.link_var, foreground="blue",
            wraplength=280, justify=tk.CENTER, cursor="hand2"
        )
        self.link_label.pack(side=tk.LEFT, expand=True, fill=tk.X)

        copy_btn = ttk.Button(link_frame, text="Copy", width=6, command=self._copy_link)
        copy_btn.pack(side=tk.RIGHT, padx=(5, 0))

        self.status_label = ttk.Label(main_frame, text="STOPPED", foreground="red")
        self.status_label.pack(pady=5)

        self.start_btn = ttk.Button(main_frame, text="Start Server", command=self._start)
        self.start_btn.pack(pady=15, ipadx=20, ipady=5)

        self.link_label.bind("<Button-1>", self._open_link)

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Open in browser", command=self._open_link)
        menu.add_command(label="Copy link", command=self._copy_link)
        self._context_menu = menu
        self.link_label.bind("<Button-3>", self._show_menu)

    # --- Callbacks ---
    def _set_link(self, text: str, url: str = "") -> None:
        self._url = url
        self.link_var.set(text)

    def _refresh_monitors(self) -> None:
        if not config.stop_event.is_set():
            self._set_link("Stop server before refreshing")
            return
        try:
            new_list = cache_monitors(get_available_monitors())
        except Exception as e:
            logger.exception("Failed to refresh monitors: %s", e)
            self._set_link(f"Error refreshing: {e}")
            return
        self.monitor_combo.config(values=[m["label"] for m in new_list])
        if new_list:
            self.monitor_label_var.set(new_list[0]["label"])
            with config.lock:
                config.config["monitor_idx"] = new_list[0]["idx"]
        self._set_link(f"Found {len(new_list)} monitor(s)")
        logger.info("Refreshed monitors: %d found", len(new_list))

    def _on_slider(self, var: Any, label: Any, key: str) -> None:
        try:
            val = int(var.get())
            label.config(text=str(val))
            with config.lock:
                config.config[key] = val  # type: ignore
        except Exception as e:
            logger.debug("%s change error: %s", key, e)

    def _on_cursor_toggle(self, *args: Any) -> None:
        with config.lock:
            config.config["show_cursor"] = bool(self.show_cursor.get())

    def _on_monitor_change(self, *args: Any) -> None:
        try:
            label = self.monitor_label_var.get()
            idx = config.label_to_idx.get(label)
            if idx is None:
                idx = int(label.split(":")[0].strip())
            with config.lock:
                config.config["monitor_idx"] = int(idx)
        except Exception as e:
            logger.debug("Monitor change error: %s", e)

    def _toggle_code(self) -> None:
        hidden = self.access_entry.cget("show") == "*"
        self.access_entry.config(show="" if hidden else "*")
        self.toggle_btn.config(text="Hide" if hidden else "Show")

    def _generate_code(self) -> None:
        new_code = config.generate_access_code(8)
        self.access_code_var.set(new_code)
        self.access_entry.config(show="")
        self.toggle_btn.config(text="Hide")
        logger.info("Generated new access code")

    def _on_access_code_change(self, *args: Any) -> None:
        with config.lock:
            config.config["access_code"] = self.access_code_var.get().strip()

    def _copy_link(self) -> None:
        url = self._url.strip()
        if not url.startswith("http"):
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(url)
            self.update()
            self.link_var.set(url + "  (copied)")
            self.after(1500, lambda: self.link_var.set(url))
        except Exception as e:
            logger.debug("Copy failed: %s", e)

    def _open_link(self, event: Optional[Any] = None) -> str:
        if self._url.startswith("http"):
            try:
                webbrowser.open(self._url, new=2)
            except Exception as e:
                logger.exception("Failed to open browser: %s", e)
                self._set_link(f"Failed to open: {e}")
        return "break"

    def _show_menu(self, e: Any) -> None:
        if self._url.startswith("http"):
            try:
                self._context_menu.post(e.x_root, e.y_root)
            except Exception as e:
                logger.debug("Menu show error: %s", e)

    # --- Server control ---
    def _parse_port(self) -> int:
        port = int(self.port_var.get())
        if not (1 <= port <= 65535):
            raise ValueError("Port must be 1-65535")
        return port

    def _resolve_monitor(self) -> int:
        label = self.monitor_label_var.get()
        idx = config.label_to_idx.get(label)
        if idx is None:
            idx = int(label.split(":")[0].strip())
        return int(idx)

    def _wait_server_ready(self, th: threading.Thread) -> bool:
        for _ in range(10):
            time.sleep(0.15)
            with config.server_lock:
                if config.server is not None:
                    return True
            if not th.is_alive():
                return False
        return False

    def _start(self) -> None:
        if not config.stop_event.is_set():
            logger.debug("Start ignored - already running")
            return
        # Ensure previous threads fully terminated before starting new ones
        for name in ("server_thread", "producer_thread"):
            th = getattr(config, name)
            if th and th.is_alive():
                logger.warning("Previous %s still alive, waiting 2s", name)
                th.join(timeout=2.0)
                if th.is_alive():
                    self._set_link(f"Error: previous {name} still stopping, try again")
                    return
                setattr(config, name, None)
        try:
            port = self._parse_port()
        except ValueError as e:
            self._set_link(f"Invalid port: {e}")
            return

        fps = int(self.fps_var.get())
        quality = int(self.quality_var.get())
        try:
            monitor_idx = self._resolve_monitor()
        except Exception as e:
            logger.debug("Monitor idx parse fallback: %s", e)
            monitor_idx = 0

        # Pre-check port synchronously to avoid thread bind race
        try:
            _check_port_available(port)
        except OSError as e:
            self._set_link(f"Port {port} busy: {e}")
            return

        with config.lock:
            config.config["fps"] = fps
            config.config["quality"] = quality
            config.config["show_cursor"] = bool(self.show_cursor.get())
            config.config["monitor_idx"] = monitor_idx
            config.config["access_code"] = self.access_code_var.get().strip()

        cam = None
        try:
            cam = create_camera(monitor_idx)
            cam.start(target_fps=fps, video_mode=True)
            with config.lock:
                config.camera = cam
            config.next_generation()  # reset buffer so consumers never replay stale frames
            config.set_running(True)
            logger.info("Camera started on monitor %d fps=%d", monitor_idx, fps)

            # Start sole pacer: producer thread (capture + encode)
            prod_th = threading.Thread(target=producer_loop, daemon=True)
            config.producer_thread = prod_th
            prod_th.start()

            # Clear stale server reference before starting new thread
            with config.server_lock:
                config.server = None
            th = threading.Thread(target=run_server, args=(port,), daemon=True)
            config.server_thread = th
            th.start()
            server_ready = self._wait_server_ready(th)
            if not th.is_alive():
                with config.server_lock:
                    srv = config.server
                if srv is None and config.HAS_WERKZEUG:
                    raise RuntimeError("Server failed to start (port busy or permission?)")
            elif not server_ready:
                logger.debug("Server thread alive but not yet ready after 1.5s")

            ip = get_ip()
            base = f"http://{ip}:{port}"
            with config.lock:
                code = config.config["access_code"]
            link = f"{base}/?code={code}" if code else base
            if code:
                logger.info("Video URL: %s/video?code=%s", base, code)
            self._set_link(link, link)
            self.status_label.config(text="RUNNING", foreground="green")
            self.start_btn.config(text="Stop Server", command=self._stop)
            logger.info("Server started on %s:%d", ip, port)
        except Exception as e:
            logger.exception("Failed to start server")
            config.set_running(False)
            config.wake_all()
            prod = config.producer_thread
            if prod and prod.is_alive():
                prod.join(timeout=2.0)
            if config.producer_thread and not config.producer_thread.is_alive():
                config.producer_thread = None
            with config.lock:
                cur_cam = config.camera
            _release_cam(cur_cam)
            if cam is not None and cam is not cur_cam:
                _release_cam(cam)
            with config.server_lock:
                srv = config.server
            if srv is not None and config.HAS_WERKZEUG:
                try:
                    srv.shutdown()
                except Exception as ex:
                    logger.debug("Server shutdown error: %s", ex)
                with config.server_lock:
                    if config.server is srv:
                        config.server = None
            self._set_link(f"Error: {e}")
            self.status_label.config(text="ERROR", foreground="red")

    def _stop(self) -> None:
        was_running = not config.stop_event.is_set()
        config.set_running(False)
        logger.info("Stopping server (was_running=%s)", was_running)

        # Stop order: producer -> server -> camera (wake blocked threads first)
        config.wake_all()
        prod = config.producer_thread
        if prod and prod.is_alive():
            prod.join(timeout=2.0)
            if prod.is_alive():
                logger.warning("Producer thread did not exit in 2s")
        if config.producer_thread and not config.producer_thread.is_alive():
            config.producer_thread = None

        # Synchronous shutdown - avoids stale keep-alive sockets stuttering on restart
        srv = None
        with config.server_lock:
            srv = config.server
        if srv is not None:
            if config.HAS_WERKZEUG and was_running:
                try:
                    srv.shutdown()
                    logger.info("Server shutdown called")
                except Exception as ex:
                    logger.debug("Server shutdown error: %s", ex)
            th = config.server_thread
            if th and th.is_alive():
                th.join(timeout=2.5 if was_running else 1.0)
                if th.is_alive():
                    logger.warning("Server thread did not exit in time")
            with config.server_lock:
                if config.server is srv:
                    config.server = None
        if config.server_thread and not config.server_thread.is_alive():
            config.server_thread = None

        with config.lock:
            cam = config.camera
        if cam is not None:
            logger.info("Camera stopped")
        _release_cam(cam)
        self._set_link("Server stopped")
        self.status_label.config(text="STOPPED", foreground="red")
        self.start_btn.config(text="Start Server", command=self._start)

    def _on_closing(self) -> None:
        logger.info("Window closing")
        self._stop()
        self.destroy()


def create_gui() -> App:
    """Backward-compatible factory - returns App instance."""
    return App()
