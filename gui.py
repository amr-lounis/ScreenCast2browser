"""
gui.py - Tkinter control panel
"""
import time
import threading
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
    access_code_var = tk.StringVar(value="1234")
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
        if config.is_running:
            link_var.set("Stop server before refreshing")
            return
        new_list = get_available_monitors()
        config.available_monitors[:] = new_list
        config.label_to_idx.clear()
        config.label_to_idx.update({m["label"]: m["idx"] for m in new_list})
        config.idx_to_label.clear()
        config.idx_to_label.update({m["idx"]: m["label"] for m in new_list})
        monitor_combo.config(values=[m["label"] for m in new_list])
        if new_list:
            monitor_label_var.set(new_list[0]["label"])
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
        config.config["quality"] = int(quality_var.get())
    quality_var.trace_add("write", on_quality_change)

    def on_cursor_toggle(*args):
        config.config["show_cursor"] = bool(show_cursor.get())
    show_cursor.trace_add("write", on_cursor_toggle)

    def on_monitor_change(*args):
        try:
            label = monitor_label_var.get()
            idx = config.label_to_idx.get(label)
            if idx is not None:
                config.config["monitor_idx"] = int(idx)
            else:
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
    access_entry = ttk.Entry(row5, textvariable=access_code_var, width=18, show="*")
    access_entry.pack(side=tk.RIGHT)

    def toggle_code():
        access_entry.config(show="" if access_entry.cget("show") == "*" else "*")
        toggle_btn.config(text="Hide" if access_entry.cget("show") == "" else "Show")
    toggle_btn = ttk.Button(row5, text="Show", width=6, command=toggle_code)
    toggle_btn.pack(side=tk.RIGHT, padx=(5, 0))
    ttk.Label(main_frame, text="Empty = no protection", font=('Arial', 7), foreground="gray").pack(anchor=tk.W)

    def on_access_code_change(*args):
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

    # Start/Stop logic
    def start():
        if config.is_running:
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

        config.config["fps"] = fps
        config.config["quality"] = quality
        config.config["show_cursor"] = bool(show_cursor.get())
        config.config["monitor_idx"] = monitor_idx
        config.config["access_code"] = access_code_var.get().strip()

        try:
            cam = dxcam.create(output_idx=monitor_idx)
            if cam is None:
                raise RuntimeError(f"Cannot create capture for monitor {monitor_idx} (not found)")
            cam.start(target_fps=fps, video_mode=True)
            config.camera = cam
            config.is_running = True

            config.server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
            config.server_thread.start()
            time.sleep(0.5)
            if config.server_thread and not config.server_thread.is_alive() and config.HAS_WERKZEUG:
                raise RuntimeError("Server failed to start (port busy?)")

            ip = get_ip()
            base = f"http://{ip}:{port}"
            code = config.config["access_code"]
            link = f"{base}/?code={code}" if code else base
            if code:
                print(f"Video URL: {base}/video?code={code}")
            link_var.set(link)
            status_label.config(text="RUNNING", foreground="green")
            start_btn.config(text="Stop Server", command=stop)
        except Exception as e:
            config.is_running = False
            if config.camera:
                try: config.camera.stop()
                except Exception: pass
                config.camera = None
            if config.HAS_WERKZEUG and config.server:
                try: config.server.shutdown()
                except Exception: pass
            link_var.set(f"Error: {e}")
            status_label.config(text="ERROR", foreground="red")

    def stop():
        config.is_running = False
        time.sleep(0.2)
        if config.HAS_WERKZEUG and config.server:
            try: config.server.shutdown()
            except Exception: pass
            config.server = None
        if config.camera:
            try: config.camera.stop()
            except Exception: pass
            try: del config.camera
            except Exception: pass
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
