import ctypes
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
import sys

import mss
import mss.tools


MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
HOTKEYS = (
    (1, MOD_CONTROL),
    (2, MOD_CONTROL | MOD_SHIFT),
)
VK_OEM_3 = 0xC0
WM_HOTKEY = 0x0312
APP_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
SCREENSHOT_DIR = APP_DIR / "screenshots"


def register_hotkey(user32):
    user32.RegisterHotKey.argtypes = [
        wintypes.HWND,
        ctypes.c_int,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.RegisterHotKey.restype = wintypes.BOOL
    registered = []
    errors = []
    for hotkey_id, modifiers in HOTKEYS:
        if user32.RegisterHotKey(
            None, hotkey_id, modifiers | MOD_NOREPEAT, VK_OEM_3
        ):
            registered.append(hotkey_id)
        else:
            errors.append(ctypes.get_last_error())
    if not registered:
        raise ctypes.WinError(errors[0])
    return registered


def listen_for_hotkey(user32, registered_hotkeys):
    user32.GetMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.GetMessageW.restype = ctypes.c_int

    message = wintypes.MSG()
    while True:
        result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
        if result == -1:
            raise ctypes.WinError(ctypes.get_last_error())
        if result == 0:
            return
        if message.message == WM_HOTKEY and message.wParam in registered_hotkeys:
            save_screenshot()


def save_screenshot():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    filename = datetime.now().strftime("screenshot_%Y%m%d_%H%M%S_%f.png")
    destination = SCREENSHOT_DIR / filename

    with mss.MSS() as capture:
        monitors = capture.monitors[1:]
        primary = next(
            (monitor for monitor in monitors if monitor.get("is_primary")),
            None,
        )
        if primary is None:
            primary = next(
                (
                    monitor
                    for monitor in monitors
                    if monitor["left"] <= 0 < monitor["left"] + monitor["width"]
                    and monitor["top"] <= 0 < monitor["top"] + monitor["height"]
                ),
                None,
            )
        if primary is None:
            raise RuntimeError("Could not identify the primary display.")
        image = capture.grab(primary)
        mss.tools.to_png(image.rgb, image.size, output=str(destination))

    print(f"Screenshot saved: {destination}")


def main():
    if not hasattr(ctypes, "WinDLL"):
        raise OSError("This global-hotkey script only works on Windows.")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    registered_hotkeys = register_hotkey(user32)
    print(
        f"Listening for Ctrl+` and Ctrl+Shift+`. "
        f"Saving screenshots to: {SCREENSHOT_DIR}"
    )
    try:
        listen_for_hotkey(user32, registered_hotkeys)
    except KeyboardInterrupt:
        pass
    finally:
        for hotkey_id in registered_hotkeys:
            user32.UnregisterHotKey(None, hotkey_id)


if __name__ == "__main__":
    main()
