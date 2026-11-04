"""
Cross-platform active window and process detection.
Supports Windows, Linux (X11 & Wayland), and macOS.
Retrieves title, process name, PID, UI control under cursor, and window bounds.
"""

import sys
import subprocess
import os
from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class WindowDetails:
    """Rich active window metadata that also unpacks as (title, process_name) tuple."""
    title: str = "Unknown Window"
    process_name: str = "Unknown Process"
    pid: Optional[int] = None
    ui_control: Optional[str] = None
    window_rect: Optional[Tuple[int, int, int, int]] = None  # (left, top, width, height)
    relative_cursor: Optional[Tuple[int, int]] = None

    def __iter__(self):
        """Allows `title, process_name = get_active_window_info()` to work seamlessly."""
        return iter((self.title, self.process_name))


def get_active_window_info(cursor_pos: Optional[Tuple[int, int]] = None) -> WindowDetails:
    """
    Returns WindowDetails containing window_title, process_name, pid, ui_control, bounds.
    Can be unpacked directly into (title, process_name) for backward compatibility.
    """
    platform = sys.platform

    if platform == "win32":
        return _get_windows_window_info(cursor_pos)
    elif platform.startswith("linux"):
        return _get_linux_window_info(cursor_pos)
    elif platform == "darwin":
        return _get_macos_window_info(cursor_pos)
    return WindowDetails()


def _get_windows_window_info(cursor_pos: Optional[Tuple[int, int]] = None) -> WindowDetails:
    """Retrieve detailed active window and control info on Windows using ctypes."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return WindowDetails(title="Desktop", process_name="explorer.exe", pid=0)

        # 1. Get window title
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
        else:
            title = "Untitled Window"

        # 2. Get process ID and image name
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = "Unknown"
        h_process = kernel32.OpenProcess(0x1000, False, pid.value)
        if h_process:
            try:
                proc_buff = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                kernel32.QueryFullProcessImageNameW.argtypes = [
                    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
                ]
                if kernel32.QueryFullProcessImageNameW(h_process, 0, proc_buff, ctypes.byref(size)):
                    full_path = proc_buff.value
                    process_name = os.path.basename(full_path)
            finally:
                kernel32.CloseHandle(h_process)

        # 3. Get window bounds
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = max(0, rect.right - rect.left)
        h = max(0, rect.bottom - rect.top)
        window_rect = (rect.left, rect.top, w, h)

        # 4. Calculate relative cursor position & detect UI control
        rel_cursor = None
        ui_control = None

        if cursor_pos:
            cx, cy = cursor_pos
            rel_cursor = (cx - rect.left, cy - rect.top)

            # Inspect child control under cursor
            pt = wintypes.POINT(cx, cy)
            hwnd_child = user32.WindowFromPoint(pt)
            if hwnd_child:
                cbuff = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd_child, cbuff, 256)
                cls_name = cbuff.value

                tbuff = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd_child, tbuff, 256)
                ctrl_txt = tbuff.value.strip()

                if ctrl_txt:
                    ui_control = f"'{ctrl_txt}' ({cls_name})"
                else:
                    ui_control = f"{cls_name}"

        return WindowDetails(
            title=title,
            process_name=process_name,
            pid=pid.value,
            ui_control=ui_control,
            window_rect=window_rect,
            relative_cursor=rel_cursor
        )
    except Exception:
        return WindowDetails(title="Active Window", process_name="Unknown")


def _get_linux_window_info(cursor_pos: Optional[Tuple[int, int]] = None) -> WindowDetails:
    """Retrieve active window info on Linux via Xlib or xdotool."""
    title = "Unknown Window"
    process_name = "Unknown"
    pid = None

    try:
        import Xlib.display
        import Xlib.X

        disp = Xlib.display.Display()
        root = disp.screen().root

        atom_active = disp.intern_atom('_NET_ACTIVE_WINDOW')
        prop = root.get_full_property(atom_active, Xlib.X.AnyPropertyType)

        if prop and prop.value:
            win_id = prop.value[0]
            if win_id == 0:
                return WindowDetails(title="Desktop / Background", process_name="desktop")

            win = disp.create_resource_object('window', win_id)

            # Try _NET_WM_NAME (UTF-8)
            atom_name = disp.intern_atom('_NET_WM_NAME')
            name_prop = win.get_full_property(atom_name, Xlib.X.AnyPropertyType)
            if name_prop and name_prop.value:
                val = name_prop.value
                title = val.decode('utf-8', errors='replace') if isinstance(val, bytes) else str(val)
            else:
                atom_wm_name = disp.intern_atom('WM_NAME')
                name_prop = win.get_full_property(atom_wm_name, Xlib.X.AnyPropertyType)
                if name_prop and name_prop.value:
                    val = name_prop.value
                    title = val.decode('utf-8', errors='replace') if isinstance(val, bytes) else str(val)

            # Try PID via _NET_WM_PID
            atom_pid = disp.intern_atom('_NET_WM_PID')
            pid_prop = win.get_full_property(atom_pid, Xlib.X.AnyPropertyType)
            if pid_prop and pid_prop.value:
                pid = pid_prop.value[0]
                try:
                    with open(f"/proc/{pid}/comm", "r") as f:
                        process_name = f.read().strip()
                except Exception:
                    pass

            return WindowDetails(
                title=title or "Active Window",
                process_name=process_name,
                pid=pid
            )
    except Exception:
        pass

    # Fallback to xdotool
    try:
        proc = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True, text=True, timeout=0.2
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return WindowDetails(title=proc.stdout.strip(), process_name="x11-app")
    except Exception:
        pass

    return WindowDetails(title="Active Application", process_name="app")


def _get_macos_window_info(cursor_pos: Optional[Tuple[int, int]] = None) -> WindowDetails:
    """Retrieve active window info on macOS using AppleScript."""
    try:
        script = 'tell application "System Events" to get name of first application process whose frontmost is true'
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=0.3
        )
        if proc.returncode == 0 and proc.stdout.strip():
            app_name = proc.stdout.strip()
            return WindowDetails(title=f"Active ({app_name})", process_name=app_name)
    except Exception:
        pass
    return WindowDetails(title="macOS Window", process_name="app")


def exclude_window_from_capture(window) -> bool:
    """
    Exclude a Tkinter window from Windows screen capture (WDA_EXCLUDEFROMCAPTURE = 0x00000011).
    Supported natively on Windows 10 (version 2004 / build 19041) and Windows 11.
    The window remains completely visible to the human user on monitor, but becomes
    completely invisible to any screenshot or recording tool (e.g. mss, BitBlt),
    preventing it from overlaying or blocking desktop content in recorded steps.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        window.update_idletasks()
        frame_hex = window.wm_frame()
        hwnd = int(frame_hex, 16) if frame_hex else window.winfo_id()
        if hwnd:
            ret = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011)
            if ret != 0:
                return True
        root_hwnd = ctypes.windll.user32.GetAncestor(window.winfo_id(), 2)  # GA_ROOT
        if root_hwnd:
            ret = ctypes.windll.user32.SetWindowDisplayAffinity(root_hwnd, 0x00000011)
            return bool(ret)
    except Exception:
        pass
    return False

