"""
monitor.py - Monitor and network discovery
"""
import socket
import dxcam
import config

# Use centralized HAS_WIN32/win32api from config (Phase 1 unification)
HAS_WIN32 = config.HAS_WIN32
win32api = config.win32api


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
                label = f"{i}: {w}x{hgt} @ ({rc[0]},{rc[1]})" + (" [Primary]" if is_primary else f" [{short_dev}]")
                monitors.append({"idx": i, "label": label, "rect": rc, "primary": is_primary})
            if monitors:
                return monitors
        except Exception:
            pass
    # Fallback: probe via dxcam
    for i in range(5):
        c = None
        try:
            c = dxcam.create(output_idx=i)
            if c is not None:
                monitors.append({"idx": i, "label": f"{i}: Monitor {i}", "rect": None, "primary": i == 0})
            else:
                # output_idx not available, try next instead of breaking (fixes missing monitor 2 when 1 absent)
                continue
        except Exception:
            continue
        finally:
            if c is not None:
                try:
                    # dxcam may need stop() before deletion to avoid thread leak
                    if hasattr(c, "stop"):
                        try:
                            c.stop()
                        except Exception:
                            pass
                    del c
                except Exception:
                    pass
    if not monitors:
        monitors = [{"idx": 0, "label": "0: Default 1920x1080", "rect": (0, 0, 1920, 1080), "primary": True}]
    return monitors


def get_monitor_offset(idx):
    """Get real offset for monitor idx - dynamic fallback, no hardcoded 1920"""
    # 1. Check cached monitors
    for m in config.available_monitors:
        if m["idx"] == idx and m["rect"]:
            return m["rect"][0], m["rect"][1]
    # 2. Try live Win32 query if available
    if HAS_WIN32 and win32api is not None:
        try:
            monitors = win32api.EnumDisplayMonitors(None, None)
            if 0 <= idx < len(monitors):
                mon_info = win32api.GetMonitorInfo(monitors[idx][0])
                rc = mon_info['Monitor']
                return rc[0], rc[1]
            # idx out of range - try to estimate from last known monitor
        except Exception:
            pass
    # 3. Estimate from cached rects (horizontal tiling assumption)
    # Find max right edge among known monitors
    max_right = None
    max_bottom = None
    for m in config.available_monitors:
        rc = m.get("rect")
        if rc:
            r = rc[2]
            b = rc[3]
            if max_right is None or r > max_right:
                max_right = r
            if max_bottom is None or b > max_bottom:
                max_bottom = b
    if max_right is not None:
        # If idx is beyond known count, place to the right of rightmost monitor
        # This is better than hardcoded 1920
        # For vertical estimation, we keep y=0
        # If we have at least one monitor, estimate as max_right for idx>=len, else 0
        known_idxs = sorted([m["idx"] for m in config.available_monitors if m.get("rect")])
        if idx not in known_idxs and max_right is not None:
            # Simple heuristic: horizontal extension
            # If idx==1 and we know idx 0 at 0,0 1920 width, max_right=1920 -> return 1920,0 (same as before but dynamic)
            # If multi-monitor, use max_right
            if idx > max(known_idxs, default=-1):
                return max_right, 0
    # 4. Fallback: origin (safe, cursor may be off but not wildly)
    return 0, 0


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
