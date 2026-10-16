"""Необов'язковий системний фон Windows із безпечним непрозорим варіантом."""

import ctypes
import sys


def apply_glass(handle: int, enabled: bool) -> bool:
    """Повертає успіх API; на інших системах інтерфейс працює без ефекту."""
    if sys.platform != "win32" or sys.getwindowsversion().build < 22621:
        return False
    try:
        dwm = ctypes.WinDLL("dwmapi")
        dwm.DwmSetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        dwm.DwmExtendFrameIntoClientArea.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        dwm.DwmExtendFrameIntoClientArea.restype = ctypes.c_long
        corners = ctypes.c_int(2)  # Округлення зовнішнього вікна Windows 11.
        dwm.DwmSetWindowAttribute(handle, 33, ctypes.byref(corners), ctypes.sizeof(corners))
        material = ctypes.c_int(3 if enabled else 1)  # Desktop Acrylic / без матеріалу.
        status = dwm.DwmSetWindowAttribute(handle, 38, ctypes.byref(material), ctypes.sizeof(material))
        margins = (ctypes.c_int * 4)(*([-1] * 4 if enabled else [0] * 4))
        frame = dwm.DwmExtendFrameIntoClientArea(handle, ctypes.byref(margins))
        return enabled and status == 0 and frame == 0
    except (OSError, AttributeError):
        return False
