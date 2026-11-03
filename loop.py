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
FORTNITE_PROCESS = "FortniteClient-Win64-Shipping.exe"
FORTNITE_URI = "com.epicgames.launcher://apps/Fortnite?action=launch&silent=true"
HOTKEY_ID = 1
WM_HOTKEY = 0x0312
MOD_CONTROL = 0x0002
VK_Q = ord("Q")


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

    try:
        while not stop_event.is_set():
            installation_info = find_fortnite_installation()
            installed = installation_info is not None

            if installed != was_installed:
                if installed:
                    installation = installation_info
                    print(f"Fortnite detected at: {installation}")
                else:
                    print("Fortnite is not installed; it cannot be launched.")
                was_installed = installed

            if installed and not is_fortnite_running():
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
            print(f"Global hotkey listener failed: {hotkey_errors[0]}")


if __name__ == "__main__":
    main()
