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
    control_type: Optional[str] = None
    control_name: Optional[str] = None
    automation_id: Optional[str] = None
    control_rect: Optional[Tuple[int, int, int, int]] = None  # (left, top, width, height) of control
    is_password: bool = False
    window_rect: Optional[Tuple[int, int, int, int]] = None  # (left, top, width, height)
    relative_cursor: Optional[Tuple[int, int]] = None

    def __iter__(self):
        """Allows `title, process_name = get_active_window_info()` to work seamlessly."""
        return iter((self.title, self.process_name))


# UIA Control Type constants for Microsoft UI Automation
UIA_CONTROL_TYPES = {
    50000: "Button", 50001: "Calendar", 50002: "CheckBox", 50003: "ComboBox",
    50004: "Edit", 50005: "Hyperlink", 50006: "Image", 50007: "ListItem",
    50008: "List", 50009: "Menu", 50010: "MenuBar", 50011: "MenuItem",
    50012: "ProgressBar", 50013: "RadioButton", 50014: "ScrollBar", 50015: "Slider",
    50016: "Spinner", 50017: "StatusBar", 50018: "Tab", 50019: "TabItem",
    50020: "Text", 50021: "ToolBar", 50022: "ToolTip", 50023: "Tree",
    50024: "TreeItem", 50025: "Custom", 50026: "Group", 50027: "Thumb",
    50028: "DataGrid", 50029: "DataItem", 50030: "Document", 50031: "SplitButton",
    50032: "Window", 50033: "Pane", 50034: "Header", 50035: "HeaderItem",
    50036: "Table", 50037: "TitleBar", 50038: "Separator"
}

_uia_instance = None
_uia_initialized = False


def _get_uia_instance():
    """Lazily initialize and return IUIAutomation instance using ctypes COM on Windows."""
    global _uia_instance, _uia_initialized
    if _uia_initialized:
        return _uia_instance
    _uia_initialized = True
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import Structure, c_void_p, byref

        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)

        class GUID(Structure):
            _fields_ = [
                ("Data1", ctypes.c_ulong),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)
            ]

        # CLSID_CUIAutomation {FF48DB42-9D38-4614-810E-9721C0F5D127}
        clsid = GUID(0xFF48DB42, 0x9D38, 0x4614, (ctypes.c_ubyte * 8)(0x81, 0x0E, 0x97, 0x21, 0xC0, 0xF5, 0xD1, 0x27))
        # IID_IUIAutomation {30CBE57D-D9D0-452A-AB13-7AC5AC4825EE}
        iid = GUID(0x30CBE57D, 0xD9D0, 0x452A, (ctypes.c_ubyte * 8)(0xAB, 0x13, 0x7A, 0xC5, 0xAC, 0x48, 0x25, 0xEE))

        p_uia = c_void_p()
        hr = ole32.CoCreateInstance(byref(clsid), None, 1 | 4, byref(iid), byref(p_uia))
        if hr == 0 and p_uia.value:
            _uia_instance = p_uia
    except Exception:
        _uia_instance = None
    return _uia_instance


def _inspect_element_via_uia(cx: int, cy: int) -> Optional[dict]:
    """Inspect element under (cx, cy) using Microsoft UI Automation (Chromium, WPF, WinUI, Office)."""
    if sys.platform != "win32":
        return None

    # Option A: Try external uiautomation package if installed
    try:
        import uiautomation as auto
        ctrl = auto.ControlFromPoint(cx, cy)
        if ctrl and ctrl.Exists(0, 0):
            rect = ctrl.BoundingRectangle
            ctrl_rect = None
            if rect:
                ctrl_rect = (rect.left, rect.top, max(0, rect.right - rect.left), max(0, rect.bottom - rect.top))
            return {
                "name": (ctrl.Name or "").strip(),
                "control_type": ctrl.ControlTypeName or "Control",
                "automation_id": getattr(ctrl, "AutomationId", "") or "",
                "rect": ctrl_rect,
                "is_password": getattr(ctrl, "IsPassword", False)
            }
    except Exception:
        pass

    # Option B: Direct native ctypes COM call to IUIAutomation
    try:
        import ctypes
        from ctypes import wintypes, Structure, c_void_p, POINTER, c_long, c_wchar_p, c_int, byref, WINFUNCTYPE, HRESULT

        p_uia = _get_uia_instance()
        if not p_uia:
            return None

        class POINT(Structure):
            _fields_ = [("x", c_long), ("y", c_long)]

        class RECT(Structure):
            _fields_ = [("left", c_long), ("top", c_long), ("right", c_long), ("bottom", c_long)]

        vtbl = ctypes.cast(p_uia, POINTER(POINTER(c_void_p))).contents
        fn_element_from_point = WINFUNCTYPE(HRESULT, c_void_p, POINT, POINTER(c_void_p))(vtbl[7])

        pt = POINT(cx, cy)
        p_elem = c_void_p()
        hr = fn_element_from_point(p_uia, pt, byref(p_elem))
        if hr != 0 or not p_elem.value:
            return None

        try:
            elem_vtbl = ctypes.cast(p_elem, POINTER(POINTER(c_void_p))).contents

            # 1. Name (index 23)
            name = ""
            try:
                fn_get_name = WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_wchar_p))(elem_vtbl[23])
                bstr_name = c_wchar_p()
                if fn_get_name(p_elem, byref(bstr_name)) == 0 and bstr_name.value:
                    name = bstr_name.value.strip()
            except Exception:
                pass

            # 2. Control Type (index 21)
            ctrl_type = "Control"
            try:
                fn_get_type = WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_long))(elem_vtbl[21])
                ctrl_type_id = c_long(0)
                if fn_get_type(p_elem, byref(ctrl_type_id)) == 0:
                    ctrl_type = UIA_CONTROL_TYPES.get(ctrl_type_id.value, "Control")
            except Exception:
                pass

            # 3. AutomationId (index 29)
            auto_id = ""
            try:
                fn_get_auto_id = WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_wchar_p))(elem_vtbl[29])
                bstr_auto_id = c_wchar_p()
                if fn_get_auto_id(p_elem, byref(bstr_auto_id)) == 0 and bstr_auto_id.value:
                    auto_id = bstr_auto_id.value.strip()
            except Exception:
                pass

            # 4. Password check (index 35)
            is_password = False
            try:
                fn_get_is_pwd = WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_int))(elem_vtbl[35])
                is_pwd_val = c_int(0)
                if fn_get_is_pwd(p_elem, byref(is_pwd_val)) == 0:
                    is_password = bool(is_pwd_val.value)
            except Exception:
                pass

            # 5. Bounding Rect (index 43)
            ctrl_rect = None
            try:
                fn_get_rect = WINFUNCTYPE(HRESULT, c_void_p, POINTER(RECT))(elem_vtbl[43])
                bound_rect = RECT()
                if fn_get_rect(p_elem, byref(bound_rect)) == 0:
                    w = max(0, bound_rect.right - bound_rect.left)
                    h = max(0, bound_rect.bottom - bound_rect.top)
                    ctrl_rect = (bound_rect.left, bound_rect.top, w, h)
            except Exception:
                pass

            return {
                "name": name,
                "control_type": ctrl_type,
                "automation_id": auto_id,
                "rect": ctrl_rect,
                "is_password": is_password
            }
        finally:
            try:
                fn_release = WINFUNCTYPE(ctypes.c_ulong, c_void_p)(elem_vtbl[2])
                fn_release(p_elem)
            except Exception:
                pass
    except Exception:
        return None


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
        ctrl_type = None
        ctrl_name = None
        auto_id = None
        ctrl_rect = None
        is_pwd = False

        if cursor_pos:
            cx, cy = cursor_pos
            rel_cursor = (cx - rect.left, cy - rect.top)

            # Option A: Deep inspection via Microsoft UI Automation
            uia_info = _inspect_element_via_uia(cx, cy)
            if uia_info and (uia_info.get("name") or uia_info.get("control_type")):
                ctrl_name = uia_info.get("name")
                ctrl_type = uia_info.get("control_type")
                auto_id = uia_info.get("automation_id")
                ctrl_rect = uia_info.get("rect")
                is_pwd = uia_info.get("is_password", False)
                if ctrl_name and ctrl_type:
                    ui_control = f"'{ctrl_name}' [{ctrl_type}]"
                elif ctrl_name:
                    ui_control = f"'{ctrl_name}'"
                elif ctrl_type:
                    ui_control = f"[{ctrl_type}]"

            # Option B: Fallback to Win32 WindowFromPoint if UIA didn't resolve named control
            if not ui_control:
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
                        ctrl_name = ctrl_txt
                    else:
                        ui_control = f"{cls_name}"
                    ctrl_type = cls_name

        return WindowDetails(
            title=title,
            process_name=process_name,
            pid=pid.value,
            ui_control=ui_control,
            control_type=ctrl_type,
            control_name=ctrl_name,
            automation_id=auto_id,
            control_rect=ctrl_rect,
            is_password=is_pwd,
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

