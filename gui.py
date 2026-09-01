"""
gui.py - Tkinter control panel
"""
import time
import threading
import secrets
import tkinter as tk
from tkinter import ttk
import webbrowser
import dxcam
import config
from monitor import get_available_monitors, get_ip, init_monitors
from server import run_server


def create_gui():
    monitors = init_monitors()
    if not monitors:
        monitors = config.available_monitors

    root = tk.Tk()
    root.title("ScreenCast->browser")
    root.geometry("420x560")
    root.resizable(False, False)

    monitor_label_var = tk.StringVar(value=monitors[0]["label"] if monitors else "0: Default")
    fps_var = tk.IntVar(value=config.config["fps"])
    quality_var = tk.IntVar(value=config.config["quality"])
    port_var = tk.StringVar(value="8080")
    show_cursor = tk.BooleanVar(value=config.config["show_cursor"])
    # Generate random code if default is still 1234 to avoid hardcoded public code
    _initial_code = config.config.get("access_code", "")
    if _initial_code == "1234":
        # keep 1234 as default for backward compat, but allow user to generate
        pass
    access_code_var = tk.StringVar(value=_initial_code)
    link_var = tk.StringVar(value="Server stopped")

    main_frame = ttk.Frame(root, padding=20)
    main_frame.pack(fill=tk.BOTH, expand=True)

    ttk.Label(main_frame, text="Display Settings", font=('Arial', 13, 'bold')).pack(pady=(0, 15))

    # Monitor row
    row1 = ttk.Frame(main_frame)
    row1.pack(fill=tk.X, pady=5)
    ttk.Label(row1, text="Monitor:").pack(side=tk.LEFT)
    monitor_combo = ttk.Combobox(row1, textvariable=monitor_label_var, values=[m["label"] for m in monitors], width=26, state="readonly")

    def refresh_monitors():
        if not config.stop_event.is_set():
            link_var.set("Stop server before refreshing")
            return
        new_list = get_available_monitors()
        with config.lock:
            config.available_monitors[:] = new_list
            config.label_to_idx.clear()
            config.label_to_idx.update({m["label"]: m["idx"] for m in new_list})
            config.idx_to_label.clear()
            config.idx_to_label.update({m["idx"]: m["label"] for m in new_list})
        monitor_combo.config(values=[m["label"] for m in new_list])
        if new_list:
            monitor_label_var.set(new_list[0]["label"])
            with config.lock:
                config.config["monitor_idx"] = new_list[0]["idx"]
        link_var.set(f"Found {len(new_list)} monitor(s)")

    refresh_btn = ttk.Button(row1, text="↻", width=3, command=refresh_monitors)
    refresh_btn.pack(side=tk.RIGHT, padx=(5, 0))
    monitor_combo.pack(side=tk.RIGHT, padx=(0, 5))

    # FPS row
    row2 = ttk.Frame(main_frame)
    row2.pack(fill=tk.X, pady=5)
    ttk.Label(row2, text="FPS:").pack(side=tk.LEFT)
    fps_label = ttk.Label(row2, text=str(config.config["fps"]))
    fps_label.pack(side=tk.RIGHT, padx=(10, 0))
    fps_scale = ttk.Scale(row2, from_=5, to=60, variable=fps_var, orient=tk.HORIZONTAL, length=130)
    fps_scale.pack(side=tk.RIGHT)

    def on_fps_change(*args):
        fps_label.config(text=str(int(fps_var.get())))
        with config.lock:
            config.config["fps"] = int(fps_var.get())
    fps_var.trace_add("write", on_fps_change)

    # Quality row
    row3 = ttk.Frame(main_frame)
    row3.pack(fill=tk.X, pady=5)
    ttk.Label(row3, text="Quality:").pack(side=tk.LEFT)
    quality_label = ttk.Label(row3, text=str(config.config["quality"]))
    quality_label.pack(side=tk.RIGHT, padx=(10, 0))
    quality_scale = ttk.Scale(row3, from_=10, to=95, variable=quality_var, orient=tk.HORIZONTAL, length=130)
    quality_scale.pack(side=tk.RIGHT)

    def on_quality_change(*args):
        quality_label.config(text=str(int(quality_var.get())))
        with config.lock:
            config.config["quality"] = int(quality_var.get())
    quality_var.trace_add("write", on_quality_change)

    def on_cursor_toggle(*args):
        with config.lock:
            config.config["show_cursor"] = bool(show_cursor.get())
    show_cursor.trace_add("write", on_cursor_toggle)

    def on_monitor_change(*args):
        try:
            label = monitor_label_var.get()
            with config.lock:
                idx = config.label_to_idx.get(label)
            if idx is not None:
                with config.lock:
                    config.config["monitor_idx"] = int(idx)
            else:
                with config.lock:
                    config.config["monitor_idx"] = int(label.split(":")[0].strip())
        except Exception:
            pass
    monitor_label_var.trace_add("write", on_monitor_change)

    ttk.Checkbutton(main_frame, text="Show Cursor", variable=show_cursor).pack(anchor=tk.W, pady=10)

    # Port
    row4 = ttk.Frame(main_frame)
    row4.pack(fill=tk.X, pady=5)
    ttk.Label(row4, text="Port:").pack(side=tk.LEFT)
    ttk.Entry(row4, textvariable=port_var, width=12).pack(side=tk.RIGHT)

    # Access Code
    row5 = ttk.Frame(main_frame)
    row5.pack(fill=tk.X, pady=5)
    ttk.Label(row5, text="Access Code:").pack(side=tk.LEFT)
    access_entry = ttk.Entry(row5, textvariable=access_code_var, width=12, show="*")
    access_entry.pack(side=tk.RIGHT)

    def toggle_code():
        access_entry.config(show="" if access_entry.cget("show") == "*" else "*")
        toggle_btn.config(text="Hide" if access_entry.cget("show") == "" else "Show")
    toggle_btn = ttk.Button(row5, text="Show", width=6, command=toggle_code)
    toggle_btn.pack(side=tk.RIGHT, padx=(5, 0))

    def generate_code():
        new_code = config.generate_access_code(8)
        access_code_var.set(new_code)
        access_entry.config(show="")
        toggle_btn.config(text="Hide")

    gen_btn = ttk.Button(row5, text="Gen", width=5, command=generate_code)
    gen_btn.pack(side=tk.RIGHT, padx=(3, 0))
    ttk.Label(main_frame, text="Empty = no protection", font=('Arial', 7), foreground="gray").pack(anchor=tk.W)

    def on_access_code_change(*args):
        with config.lock:
            config.config["access_code"] = access_code_var.get().strip()
    access_code_var.trace_add("write", on_access_code_change)

    ttk.Separator(main_frame).pack(fill=tk.X, pady=15)

    # Link row with open + copy
    link_frame = ttk.Frame(main_frame)
    link_frame.pack(fill=tk.X, pady=10)
    link_label = ttk.Label(link_frame, textvariable=link_var, foreground="blue", wraplength=280, justify=tk.CENTER, cursor="hand2")
    link_label.pack(side=tk.LEFT, expand=True, fill=tk.X)

    def copy_link():
        url = link_var.get().strip()
        if not url.startswith("http"):
            return
        try:
            root.clipboard_clear()
            root.clipboard_append(url)
            root.update()  # keep clipboard after window close
            link_var.set(url + "  (copied)")
            root.after(1500, lambda: link_var.set(url))
        except Exception:
            pass

    copy_btn = ttk.Button(link_frame, text="Copy", width=6, command=copy_link)
    copy_btn.pack(side=tk.RIGHT, padx=(5,0))

    status_label = ttk.Label(main_frame, text="STOPPED", foreground="red")
    status_label.pack(pady=5)

    # Start/Stop logic (Phase 1: thread-safe)
    def start():
        if not config.stop_event.is_set():
            return
        try:
            port = int(port_var.get())
            if not (1 <= port <= 65535):
                raise ValueError("Port must be 1-65535")
        except ValueError as e:
            link_var.set(f"Invalid port: {e}")
            return

        fps = int(fps_var.get())
        quality = int(quality_var.get())
        sel_label = monitor_label_var.get()
        monitor_idx = config.label_to_idx.get(sel_label, 0)
        try:
            if sel_label not in config.label_to_idx:
                monitor_idx = int(sel_label.split(":")[0].strip())
        except Exception:
            pass

        with config.lock:
            config.config["fps"] = fps
            config.config["quality"] = quality
            config.config["show_cursor"] = bool(show_cursor.get())
            config.config["monitor_idx"] = monitor_idx
            config.config["access_code"] = access_code_var.get().strip()

        cam = None
        try:
            cam = dxcam.create(output_idx=monitor_idx)
            if cam is None:
                raise RuntimeError(f"Cannot create capture for monitor {monitor_idx} (not found)")
            cam.start(target_fps=fps, video_mode=True)
            with config.lock:
                config.camera = cam
            config.set_running(True)

            # Start server in daemon thread; run_server will set config.server under lock
            config.server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
            config.server_thread.start()
            # Wait briefly for bind - use stop_event.wait instead of sleep to be interruptible
            # Check if thread died (port busy) - run_server raises OSError
            config.stop_event.wait(0.7)
            # If thread died quickly and server is None, likely port busy
            if config.server_thread and not config.server_thread.is_alive():
                # Thread exited - check if server was never set (bind failure)
                with config.server_lock:
                    srv = config.server
                if srv is None and config.HAS_WERKZEUG:
                    raise RuntimeError("Server failed to start (port busy or permission?)")

            ip = get_ip()
            base = f"http://{ip}:{port}"
            with config.lock:
                code = config.config["access_code"]
            link = f"{base}/?code={code}" if code else base
            if code:
                print(f"Video URL: {base}/video?code={code}")
            link_var.set(link)
            status_label.config(text="RUNNING", foreground="green")
            start_btn.config(text="Stop Server", command=stop)
        except Exception as e:
            config.set_running(False)
            # Cleanup camera - ensure stop() is called to avoid thread leak
            with config.lock:
                cur_cam = config.camera
            if cur_cam is not None:
                try:
                    cur_cam.stop()
                except Exception:
                    pass
                with config.lock:
                    config.camera = None
            # Also cleanup the local cam if different
            if cam is not None and cam is not cur_cam:
                try:
                    cam.stop()
                except Exception:
                    pass
            # Shutdown server without blocking GUI thread
            with config.server_lock:
                srv = config.server
            if srv is not None and config.HAS_WERKZEUG:
                try:
                    srv.shutdown()
                except Exception:
                    pass
                with config.server_lock:
                    if config.server is srv:
                        config.server = None
            link_var.set(f"Error: {e}")
            status_label.config(text="ERROR", foreground="red")

    def stop():
        # Idempotent stop - safe to call multiple times
        was_running = not config.stop_event.is_set()
        config.set_running(False)
        # Give generate() loop a moment to exit (non-blocking wait handled inside generate)
        # Shutdown server in background to avoid freezing GUI (shutdown can block)
        def _do_shutdown():
            with config.server_lock:
                srv = config.server
            if srv is not None and config.HAS_WERKZEUG:
                try:
                    srv.shutdown()
                except Exception:
                    pass
                # run_server's finally will clear, but also clear here
                with config.server_lock:
                    if config.server is srv:
                        config.server = None
        if was_running:
            threading.Thread(target=_do_shutdown, daemon=True).start()
        # Stop camera (may take ~100ms)
        with config.lock:
            cam = config.camera
        if cam is not None:
            try:
                cam.stop()
            except Exception:
                pass
            with config.lock:
                # double-check still same object
                if config.camera is cam:
                    config.camera = None
        link_var.set("Server stopped")
        status_label.config(text="STOPPED", foreground="red")
        start_btn.config(text="Start Server", command=start)

    def on_closing():
        stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)

    start_btn = ttk.Button(main_frame, text="Start Server", command=start)
    start_btn.pack(pady=15, ipadx=20, ipady=5)

    def open_link(event=None):
        url = link_var.get().strip()
        # remove "(copied)" suffix if present
        if "  (copied)" in url:
            url = url.replace("  (copied)", "").strip()
        if url.startswith("http"):
            try:
                webbrowser.open(url, new=2)
            except Exception as e:
                link_var.set(f"Failed to open: {e}")
        return "break"

    link_label.bind("<Button-1>", open_link)

    # Right-click menu for copy/open
    menu = tk.Menu(root, tearoff=0)
    menu.add_command(label="Open in browser", command=open_link)
    menu.add_command(label="Copy link", command=lambda: copy_link())
    def show_menu(e):
        if link_var.get().startswith("http"):
            menu.post(e.x_root, e.y_root)
    link_label.bind("<Button-3>", show_menu)

    return root
