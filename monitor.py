"""
monitor.py - Monitor and network discovery
"""
import socket
import dxcam
import config

try:
    import win32api
    HAS_WIN32 = config.HAS_WIN32
except ImportError:
    HAS_WIN32 = False
    win32api = None


def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except OSError:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP


def get_available_monitors():
    """Detect only physically available monitors"""
    monitors = []
    if HAS_WIN32:
        try:
            raw = win32api.EnumDisplayMonitors(None, None)
            for i, h in enumerate(raw):
                info = win32api.GetMonitorInfo(h[0])
                rc = info['Monitor']  # (left, top, right, bottom)
                w = rc[2] - rc[0]
                hgt = rc[3] - rc[1]
                is_primary = bool(info.get('Flags', 0) & 1)
                dev = info.get('Device', f"DISPLAY{i+1}")
                short_dev = dev.split("\\")[-1] if "\\" in dev else dev
                label = f"{i}: {w}x{h} @ ({rc[0]},{rc[1]})" + (" [Primary]" if is_primary else f" [{short_dev}]")
                monitors.append({"idx": i, "label": label, "rect": rc, "primary": is_primary})
            if monitors:
                return monitors
        except Exception:
            pass
    # Fallback: probe via dxcam
    for i in range(5):
        try:
            c = dxcam.create(output_idx=i)
            if c is not None:
                try:
                    del c
                except Exception:
                    pass
                monitors.append({"idx": i, "label": f"{i}: Monitor {i}", "rect": None, "primary": i == 0})
            else:
                break
        except Exception:
            break
    if not monitors:
        monitors = [{"idx": 0, "label": "0: Default 1920x1080", "rect": (0, 0, 1920, 1080), "primary": True}]
    return monitors


def get_monitor_offset(idx):
    """Get real offset for monitor idx"""
    for m in config.available_monitors:
        if m["idx"] == idx and m["rect"]:
            return m["rect"][0], m["rect"][1]
    if not HAS_WIN32:
        return (1920 if idx == 1 else 0, 0)
    try:
        monitors = win32api.EnumDisplayMonitors(None, None)
        if 0 <= idx < len(monitors):
            mon_info = win32api.GetMonitorInfo(monitors[idx][0])
            rc = mon_info['Monitor']
            return rc[0], rc[1]
        return (1920 if idx == 1 else 0, 0)
    except Exception:
        return (1920 if idx == 1 else 0, 0)


def init_monitors():
    """Refresh monitor cache at startup"""
    monitors = get_available_monitors()
    config.available_monitors[:] = monitors
    config.label_to_idx.clear()
    config.label_to_idx.update({m["label"]: m["idx"] for m in monitors})
    config.idx_to_label.clear()
    config.idx_to_label.update({m["idx"]: m["label"] for m in monitors})
    if monitors:
        config.config["monitor_idx"] = monitors[0]["idx"]
    return monitors
