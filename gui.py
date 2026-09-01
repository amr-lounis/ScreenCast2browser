"""
gui.py - Tkinter control panel (Phase 3: Class-based, type-hinted, logged)
"""
import logging
import threading
import time
import tkinter as tk
from tkinter import ttk
import webbrowser
from typing import List, Dict, Any, Optional

import dxcam
import config
from monitor import get_available_monitors, get_ip, init_monitors
from server import run_server, _check_port_available

logger = logging.getLogger(__name__)


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
        self.fps_var.trace_add("write", self._on_fps_change)

        # Quality row
        row3 = ttk.Frame(main_frame)
        row3.pack(fill=tk.X, pady=5)
        ttk.Label(row3, text="Quality:").pack(side=tk.LEFT)
        self.quality_label = ttk.Label(row3, text=str(config.config["quality"]))
        self.quality_label.pack(side=tk.RIGHT, padx=(10, 0))
        quality_scale = ttk.Scale(row3, from_=10, to=95, variable=self.quality_var, orient=tk.HORIZONTAL, length=130)
        quality_scale.pack(side=tk.RIGHT)
        self.quality_var.trace_add("write", self._on_quality_change)

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
    def _refresh_monitors(self) -> None:
        if not config.stop_event.is_set():
            self.link_var.set("Stop server before refreshing")
            return
        try:
            new_list = get_available_monitors()
        except Exception as e:
            logger.exception("Failed to refresh monitors: %s", e)
            self.link_var.set(f"Error refreshing: {e}")
            return
        with config.lock:
            config.available_monitors[:] = new_list
            config.label_to_idx.clear()
            config.label_to_idx.update({m["label"]: m["idx"] for m in new_list})
            config.idx_to_label.clear()
            config.idx_to_label.update({m["idx"]: m["label"] for m in new_list})
        self.monitor_combo.config(values=[m["label"] for m in new_list])
        if new_list:
            self.monitor_label_var.set(new_list[0]["label"])
            with config.lock:
                config.config["monitor_idx"] = new_list[0]["idx"]
        self.link_var.set(f"Found {len(new_list)} monitor(s)")
        logger.info("Refreshed monitors: %d found", len(new_list))

    def _on_fps_change(self, *args: Any) -> None:
        try:
            val = int(self.fps_var.get())
            self.fps_label.config(text=str(val))
            with config.lock:
                config.config["fps"] = val
        except Exception as e:
            logger.debug("FPS change error: %s", e)

    def _on_quality_change(self, *args: Any) -> None:
        try:
            val = int(self.quality_var.get())
            self.quality_label.config(text=str(val))
            with config.lock:
                config.config["quality"] = val
        except Exception as e:
            logger.debug("Quality change error: %s", e)

    def _on_cursor_toggle(self, *args: Any) -> None:
        with config.lock:
            config.config["show_cursor"] = bool(self.show_cursor.get())

    def _on_monitor_change(self, *args: Any) -> None:
        try:
            label = self.monitor_label_var.get()
            with config.lock:
                idx = config.label_to_idx.get(label)
            if idx is not None:
                with config.lock:
                    config.config["monitor_idx"] = int(idx)
            else:
                with config.lock:
                    config.config["monitor_idx"] = int(label.split(":")[0].strip())
        except Exception as e:
            logger.debug("Monitor change error: %s", e)

    def _toggle_code(self) -> None:
        show = self.access_entry.cget("show")
        self.access_entry.config(show="" if show == "*" else "*")
        self.toggle_btn.config(text="Hide" if self.access_entry.cget("show") == "" else "Show")

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
        url = self.link_var.get().strip()
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
        url = self.link_var.get().strip()
        if "  (copied)" in url:
            url = url.replace("  (copied)", "").strip()
        if url.startswith("http"):
            try:
                webbrowser.open(url, new=2)
            except Exception as e:
                logger.exception("Failed to open browser: %s", e)
                self.link_var.set(f"Failed to open: {e}")
        return "break"

    def _show_menu(self, e: Any) -> None:
        if self.link_var.get().startswith("http"):
            try:
                self._context_menu.post(e.x_root, e.y_root)
            except Exception as e:
                logger.debug("Menu show error: %s", e)

    # --- Server control ---
    def _start(self) -> None:
        if not config.stop_event.is_set():
            logger.debug("Start ignored - already running")
            return
        # Ensure previous thread fully terminated before starting new one
        old_th = config.server_thread
        if old_th and old_th.is_alive():
            logger.warning("Previous server thread still alive, waiting 2s")
            old_th.join(timeout=2.0)
            if old_th.is_alive():
                self.link_var.set("Error: previous server still stopping, try again")
                return
            config.server_thread = None
        try:
            port = int(self.port_var.get())
            if not (1 <= port <= 65535):
                raise ValueError("Port must be 1-65535")
        except ValueError as e:
            self.link_var.set(f"Invalid port: {e}")
            return

        fps = int(self.fps_var.get())
        quality = int(self.quality_var.get())
        sel_label = self.monitor_label_var.get()
        monitor_idx = config.label_to_idx.get(sel_label, 0)
        try:
            if sel_label not in config.label_to_idx:
                monitor_idx = int(sel_label.split(":")[0].strip())
        except Exception as e:
            logger.debug("Monitor idx parse fallback: %s", e)

        # Pre-check port synchronously to avoid thread bind race
        try:
            _check_port_available(port)
        except OSError as e:
            self.link_var.set(f"Port {port} busy: {e}")
            return

        with config.lock:
            config.config["fps"] = fps
            config.config["quality"] = quality
            config.config["show_cursor"] = bool(self.show_cursor.get())
            config.config["monitor_idx"] = monitor_idx
            config.config["access_code"] = self.access_code_var.get().strip()

        cam = None
        try:
            # BGRA + numpy backend (leanest)
            try:
                cam = dxcam.create(output_idx=monitor_idx, output_color="BGRA", processor_backend="numpy")
            except TypeError:
                # older dxcam without processor_backend
                cam = dxcam.create(output_idx=monitor_idx, output_color="BGRA")
            if cam is None:
                # fallback to default color if BGRA unsupported
                cam = dxcam.create(output_idx=monitor_idx)
            if cam is None:
                raise RuntimeError(f"Cannot create capture for monitor {monitor_idx} (not found)")
            cam.start(target_fps=fps, video_mode=True)
            with config.lock:
                config.camera = cam
            config.set_running(True)
            logger.info("Camera started on monitor %d fps=%d", monitor_idx, fps)

            # Clear stale server reference before starting new thread
            with config.server_lock:
                config.server = None
            th = threading.Thread(target=run_server, args=(port,), daemon=True)
            config.server_thread = th
            th.start()
            # Wait for server to bind (poll instead of blind 0.7s)
            server_ready = False
            for _ in range(10):
                time.sleep(0.15)
                with config.server_lock:
                    srv = config.server
                if srv is not None:
                    server_ready = True
                    break
                if not th.is_alive():
                    break
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
            self.link_var.set(link)
            self.status_label.config(text="RUNNING", foreground="green")
            self.start_btn.config(text="Stop Server", command=self._stop)
            logger.info("Server started on %s:%d", ip, port)
        except Exception as e:
            logger.exception("Failed to start server")
            config.set_running(False)
            with config.lock:
                cur_cam = config.camera
            if cur_cam is not None:
                try:
                    cur_cam.stop()
                except Exception as ex:
                    logger.debug("Camera stop error: %s", ex)
                for _m in ("release", "close"):
                    if hasattr(cur_cam, _m):
                        try:
                            getattr(cur_cam, _m)()
                        except Exception:
                            pass
                        break
                with config.lock:
                    config.camera = None
                try:
                    del cur_cam
                except Exception:
                    pass
            if cam is not None and cam is not cur_cam:
                try:
                    cam.stop()
                except Exception as ex:
                    logger.debug("Local cam stop error: %s", ex)
                for _m in ("release", "close"):
                    if hasattr(cam, _m):
                        try:
                            getattr(cam, _m)()
                        except Exception:
                            pass
                        break
                try:
                    del cam
                except Exception:
                    pass
            try:
                import gc

                gc.collect()
            except Exception:
                pass
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
            self.link_var.set(f"Error: {e}")
            self.status_label.config(text="ERROR", foreground="red")

    def _stop(self) -> None:
        was_running = not config.stop_event.is_set()
        config.set_running(False)
        logger.info("Stopping server (was_running=%s)", was_running)

        # Synchronous shutdown - critical to avoid stale keep-alive sockets causing stutter on restart
        srv = None
        with config.server_lock:
            srv = config.server
        if srv is not None and config.HAS_WERKZEUG and was_running:
            try:
                srv.shutdown()
                logger.info("Server shutdown called")
            except Exception as ex:
                logger.debug("Server shutdown error: %s", ex)
            th = config.server_thread
            if th and th.is_alive():
                th.join(timeout=2.5)
                if th.is_alive():
                    logger.warning("Server thread did not exit in 2.5s")
            with config.server_lock:
                if config.server is srv:
                    config.server = None
        elif srv is not None:
            with config.server_lock:
                if config.server is srv:
                    config.server = None
            th = config.server_thread
            if th and th.is_alive():
                th.join(timeout=1.0)
        # Clear thread reference if dead
        if config.server_thread and not config.server_thread.is_alive():
            config.server_thread = None

        with config.lock:
            cam = config.camera
        if cam is not None:
            try:
                cam.stop()
                logger.info("Camera stopped")
            except Exception as ex:
                logger.debug("Camera stop error: %s", ex)
            # Explicit COM release before clearing ref - prevents AV in __del__ after CoUninitialize
            for _m in ("release", "close"):
                if hasattr(cam, _m):
                    try:
                        getattr(cam, _m)()
                    except Exception:
                        pass
                    break
            with config.lock:
                if config.camera is cam:
                    config.camera = None
            try:
                del cam
            except Exception:
                pass
            try:
                import gc

                gc.collect()
            except Exception:
                pass
        self.link_var.set("Server stopped")
        self.status_label.config(text="STOPPED", foreground="red")
        self.start_btn.config(text="Start Server", command=self._start)

    def _on_closing(self) -> None:
        logger.info("Window closing")
        self._stop()
        self.destroy()


def create_gui() -> App:
    """Backward-compatible factory - returns App instance."""
    return App()
