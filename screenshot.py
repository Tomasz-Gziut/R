import ctypes
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
import sys
import time

import mss
import mss.tools
import cv2


RUN_INTERVAL_SECONDS = 10
REFERENCE_SIZE = (2559, 1437)
MATCH_REGION = (0.66, 0.43, 0.97, 0.59)
MATCH_SCALES = tuple(index / 100 for index in range(85, 116, 5))
MATCH_THRESHOLD = 0.88
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
APP_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
SCREENSHOT_DIR = Path(r"C:\Screenshots")
TEMPLATE_PATH = RESOURCE_DIR / "assets" / "replay_button.png"


def find_replay_button(screenshot_path):
    screenshot = cv2.imread(str(screenshot_path), cv2.IMREAD_COLOR)
    template = cv2.imread(str(TEMPLATE_PATH), cv2.IMREAD_COLOR)
    if screenshot is None:
        raise OSError(f"Could not read screenshot: {screenshot_path}")
    if template is None:
        raise OSError(f"Could not read button template: {TEMPLATE_PATH}")

    screen_height, screen_width = screenshot.shape[:2]
    left = round(MATCH_REGION[0] * screen_width)
    top = round(MATCH_REGION[1] * screen_height)
    right = round(MATCH_REGION[2] * screen_width)
    bottom = round(MATCH_REGION[3] * screen_height)
    region = screenshot[top:bottom, left:right]
    scale_x = screen_width / REFERENCE_SIZE[0]
    scale_y = screen_height / REFERENCE_SIZE[1]
    best_score = -1.0
    best_location = None

    for scale in MATCH_SCALES:
        target_width = round(template.shape[1] * scale_x * scale)
        target_height = round(template.shape[0] * scale_y * scale)
        if target_width > region.shape[1] or target_height > region.shape[0]:
            continue
        resized = cv2.resize(
            template, (target_width, target_height), interpolation=cv2.INTER_AREA
        )
        result = cv2.matchTemplate(region, resized, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(result)
        if score > best_score:
            best_score = score
            best_location = (
                left + location[0] + target_width // 2,
                top + location[1] + target_height // 2,
            )

    if best_score < MATCH_THRESHOLD:
        return None
    return best_location


def click_position(user32, monitor, position):
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.SetCursorPos.restype = wintypes.BOOL
    user32.mouse_event.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_size_t,
    ]
    user32.mouse_event.restype = None
    if not user32.SetCursorPos(
        monitor["left"] + position[0], monitor["top"] + position[1]
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


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

    print(f"Screenshot saved: {destination}", flush=True)
    try:
        button_position = find_replay_button(destination)
        print(button_position is not None, flush=True)
        if button_position is not None:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            click_position(user32, primary, button_position)
            print(f"Clicked replay button at {button_position}", flush=True)
    finally:
        destination.unlink(missing_ok=True)
        print(f"Deleted screenshot: {destination}", flush=True)


def run_periodically():
    while True:
        started = time.monotonic()
        save_screenshot()
        remaining = RUN_INTERVAL_SECONDS - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(remaining)


def main():
    if not hasattr(ctypes, "WinDLL"):
        raise OSError("This global-hotkey script only works on Windows.")

    print(
        f"Checking for the replay button every {RUN_INTERVAL_SECONDS} seconds. "
        f"Screenshots: {SCREENSHOT_DIR}",
        flush=True,
    )
    run_periodically()


if __name__ == "__main__":
    main()
