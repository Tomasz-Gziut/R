import ctypes
import csv
import json
import os
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path


CHECK_INTERVAL = 5
LAUNCH_RETRY_INTERVAL = 60
GAME_AUTOMATION_TIMEOUT = 600
SCREEN_CHECK_INTERVAL = 1
ESCAPE_INTERVAL = 2
MAX_ESCAPE_PRESSES = 10
HEADER_MATCH_THRESHOLD = 0.82
FORTNITE_PROCESS = "FortniteClient-Win64-Shipping.exe"
FORTNITE_URI = "com.epicgames.launcher://apps/Fortnite?action=launch&silent=true"
HEADER_TEMPLATE = Path(__file__).parent / "assets" / "battle_royale_header.png"
HOTKEY_ID = 1
WM_HOTKEY = 0x0312
MOD_CONTROL = 0x0002
VK_Q = ord("Q")
VK_ESCAPE = 0x1B
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def get_user32():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.RECT),
    ]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.keybd_event.argtypes = [
        wintypes.BYTE,
        wintypes.BYTE,
        wintypes.DWORD,
        ctypes.c_size_t,
    ]
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.SetCursorPos.restype = wintypes.BOOL
    user32.mouse_event.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_size_t,
    ]
    return user32


def find_fortnite_window(user32):
    process_id = subprocess.run(
        [
            "tasklist",
            "/FI",
            f"IMAGENAME eq {FORTNITE_PROCESS}",
            "/FO",
            "CSV",
            "/NH",
        ],
        capture_output=True,
        text=True,
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    process_ids = {
        int(row[1])
        for row in csv.reader(process_id.stdout.splitlines())
        if len(row) > 1 and row[0].casefold() == FORTNITE_PROCESS.casefold()
    }
    if not process_ids:
        return None

    candidates = []
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    def visit_window(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True

        owner_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        if owner_pid.value not in process_ids:
            return True

        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width >= 640 and height >= 400:
            candidates.append((width * height, hwnd))
        return True

    callback = callback_type(visit_window)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    if not user32.EnumWindows(callback, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return max(candidates, key=lambda candidate: candidate[0], default=(0, None))[1]


def is_foreground_window(user32, hwnd):
    foreground = user32.GetForegroundWindow()
    if not foreground:
        return False
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(foreground, ctypes.byref(process_id))
    return process_id.value == get_window_process_id(user32, hwnd)


def get_window_process_id(user32, hwnd):
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    return process_id.value


def capture_game_monitor(user32, hwnd):
    import numpy
    from mss import MSS

    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError(ctypes.get_last_error())
    center_x = (rect.left + rect.right) // 2
    center_y = (rect.top + rect.bottom) // 2

    with MSS() as capture:
        monitor = next(
            (
                item
                for item in capture.monitors[1:]
                if item["left"] <= center_x < item["left"] + item["width"]
                and item["top"] <= center_y < item["top"] + item["height"]
            ),
            capture.monitors[1],
        )
        screenshot = numpy.asarray(capture.grab(monitor))
    return screenshot, monitor


def find_battle_royale_play_button(screenshot, template, cv2, numpy):
    screen_height, screen_width = screenshot.shape[:2]
    gray = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2GRAY)
    search_region = gray[:, : int(screen_width * 0.48)]
    best_match = None

    for scale in numpy.arange(0.55, 1.46, 0.05):
        width = round(template.shape[1] * scale)
        height = round(template.shape[0] * scale)
        if width > search_region.shape[1] or height > search_region.shape[0]:
            continue
        resized = cv2.resize(
            template,
            (width, height),
            interpolation=(
                cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
            ),
        )
        matches = cv2.matchTemplate(
            search_region, resized, cv2.TM_CCOEFF_NORMED
        )
        _, score, _, location = cv2.minMaxLoc(matches)
        if best_match is None or score > best_match[0]:
            best_match = (score, location, (width, height))

    if best_match is None or best_match[0] < HEADER_MATCH_THRESHOLD:
        return None

    score, (header_x, header_y), (header_width, header_height) = best_match
    bgr = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(
        hsv,
        numpy.array([20, 120, 170], dtype=numpy.uint8),
        numpy.array([40, 255, 255], dtype=numpy.uint8),
    )
    yellow = yellow[:, : int(screen_width * 0.48)]
    contours, _ = cv2.findContours(
        yellow, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    buttons = []
    header_center = header_x + header_width / 2
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        aspect_ratio = width / height if height else 0
        if not 0.75 <= width / header_width <= 1.8:
            continue
        if not 2.5 <= aspect_ratio <= 6.5:
            continue
        if not 0.025 <= height / screen_height <= 0.12:
            continue
        if y < header_y + header_height:
            continue
        if abs(x + width / 2 - header_center) > header_width * 0.45:
            continue
        buttons.append((y, x, width, height))

    if not buttons:
        return None

    button_y, x, width, height = max(buttons)
    return (x + width // 2, button_y + height // 2), score


def press_escape(user32):
    user32.keybd_event(VK_ESCAPE, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)


def click_play_button(user32, x, y):
    if not user32.SetCursorPos(x, y):
        raise ctypes.WinError(ctypes.get_last_error())
    time.sleep(0.15)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.08)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def automate_fortnite_lobby(stop_event):
    import cv2
    import numpy
    from mss import MSS

    template = cv2.imread(str(HEADER_TEMPLATE), cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise RuntimeError(f"Could not read the image template: {HEADER_TEMPLATE}")

    user32 = get_user32()
    deadline = time.monotonic() + GAME_AUTOMATION_TIMEOUT
    last_escape = 0
    escape_presses = 0
    last_window = None
    stable_window_checks = 0
    print("Waiting for Fortnite's game window to finish starting.")

    while not stop_event.is_set() and time.monotonic() < deadline:
        hwnd = find_fortnite_window(user32)
        if hwnd is None:
            stable_window_checks = 0
            stop_event.wait(SCREEN_CHECK_INTERVAL)
            continue

        if hwnd != last_window:
            last_window = hwnd
            stable_window_checks = 0
        if not is_foreground_window(user32, hwnd):
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
            stop_event.wait(SCREEN_CHECK_INTERVAL)
            continue

        stable_window_checks += 1
        if stable_window_checks < 2:
            stop_event.wait(SCREEN_CHECK_INTERVAL)
            continue

        screenshot, monitor = capture_game_monitor(user32, hwnd)
        target = find_battle_royale_play_button(
            screenshot, template, cv2, numpy
        )
        if target:
            (x, y), confidence = target
            click_play_button(
                user32, monitor["left"] + x, monitor["top"] + y
            )
            print(
                "Battle Royale screen detected "
                f"(match {confidence:.0%}); clicked the yellow Play button."
            )
            return

        now = time.monotonic()
        if (
            escape_presses < MAX_ESCAPE_PRESSES
            and now - last_escape >= ESCAPE_INTERVAL
        ):
            press_escape(user32)
            escape_presses += 1
            last_escape = now
            print(
                f"Battle Royale screen not ready; pressed Esc "
                f"({escape_presses}/{MAX_ESCAPE_PRESSES})."
            )
        stop_event.wait(SCREEN_CHECK_INTERVAL)

    if not stop_event.is_set():
        print(
            "Battle Royale screen was not detected before the "
            "10-minute automation timeout."
        )


def run_fortnite_lobby_automation(stop_event):
    try:
        automate_fortnite_lobby(stop_event)
    except (ImportError, OSError, RuntimeError) as error:
        print(f"Fortnite screen automation failed: {error}")


def find_fortnite_installation():
    program_data = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
    manifests = (
        program_data
        / "Epic"
        / "EpicGamesLauncher"
        / "Data"
        / "Manifests"
    )

    for manifest_path in manifests.glob("*.item"):
        try:
            with manifest_path.open(encoding="utf-8") as manifest_file:
                manifest = json.load(manifest_file)
        except (OSError, json.JSONDecodeError):
            continue

        if manifest.get("AppName") != "Fortnite":
            continue

        install_location = manifest.get("InstallLocation")
        if not install_location:
            continue

        installation = Path(install_location)
        if not installation.is_dir():
            continue

        return installation

    return None


def is_fortnite_running():
    result = subprocess.run(
        [
            "tasklist",
            "/FI",
            f"IMAGENAME eq {FORTNITE_PROCESS}",
            "/FO",
            "CSV",
            "/NH",
        ],
        capture_output=True,
        text=True,
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return any(
        row and row[0].casefold() == FORTNITE_PROCESS.casefold()
        for row in csv.reader(result.stdout.splitlines())
    )


def close_fortnite():
    if not is_fortnite_running():
        return

    result = subprocess.run(
        ["taskkill", "/IM", FORTNITE_PROCESS, "/T", "/F"],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(detail or "taskkill could not close Fortnite.")


def listen_for_quit(stop_event, ready_event, errors):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.RegisterHotKey.argtypes = [
        wintypes.HWND,
        ctypes.c_int,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.GetMessageW.restype = ctypes.c_int

    registered = False
    try:
        if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL, VK_Q):
            raise ctypes.WinError(ctypes.get_last_error())
        registered = True
        ready_event.set()

        message = wintypes.MSG()
        while True:
            result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
            if result == -1:
                raise ctypes.WinError(ctypes.get_last_error())
            if result == 0:
                break
            if message.message == WM_HOTKEY and message.wParam == HOTKEY_ID:
                try:
                    close_fortnite()
                except (OSError, RuntimeError) as error:
                    errors.append(error)
                stop_event.set()
                break
    except OSError as error:
        errors.append(error)
        stop_event.set()
    finally:
        if registered:
            user32.UnregisterHotKey(None, HOTKEY_ID)
        ready_event.set()


def main():
    stop_event = threading.Event()
    ready_event = threading.Event()
    hotkey_errors = []
    hotkey_thread = threading.Thread(
        target=listen_for_quit,
        args=(stop_event, ready_event, hotkey_errors),
        daemon=True,
    )
    hotkey_thread.start()
    ready_event.wait()
    if hotkey_errors:
        raise RuntimeError(
            f"Could not register Ctrl+Q as a global hotkey: {hotkey_errors[0]}"
        )

    print("Fortnite monitor running. Press Ctrl+Q anywhere to quit, or Ctrl+C.")
    last_launch = None
    was_installed = None
    game_was_running = False
    automation_thread = None

    try:
        while not stop_event.is_set():
            installation_info = find_fortnite_installation()
            installed = installation_info is not None
            game_running = is_fortnite_running()

            if installed != was_installed:
                if installed:
                    installation = installation_info
                    print(f"Fortnite detected at: {installation}")
                else:
                    print("Fortnite is not installed; it cannot be launched.")
                was_installed = installed

            if game_running and not game_was_running:
                if automation_thread is None or not automation_thread.is_alive():
                    automation_thread = threading.Thread(
                        target=run_fortnite_lobby_automation,
                        args=(stop_event,),
                        daemon=True,
                    )
                    automation_thread.start()
                game_was_running = True
            elif not game_running:
                game_was_running = False

            if installed and not game_running:
                now = time.monotonic()
                if last_launch is None or now - last_launch >= LAUNCH_RETRY_INTERVAL:
                    installation = installation_info
                    try:
                        print(
                            "Launching Fortnite through Epic Games Launcher "
                            f"(installed at: {installation})."
                        )
                        os.startfile(FORTNITE_URI)
                    except OSError as error:
                        print(f"Could not launch Fortnite: {error}")
                    last_launch = now

            stop_event.wait(CHECK_INTERVAL)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        print("Fortnite monitor stopped.")
        if hotkey_errors:
            print(f"Ctrl+Q action failed: {hotkey_errors[0]}")


if __name__ == "__main__":
    main()
