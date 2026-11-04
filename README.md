# Screenshot hotkey

Install the dependency and start the listener:

```sh
py -m pip install -r requirements.txt
py screenshot.py
```

To build a standalone Windows executable, run `build_exe.bat`. It installs
PyInstaller if needed and creates `ScreenshotHotkey.exe` in the repository
root (and a copy in `dist\`). Run it and leave it open to keep the hotkey
active; captures are saved in the `screenshots` folder beside the executable.

While it is running, press **Ctrl+`** or **Ctrl+Shift+`** (the backtick/tilde
key) anywhere on Windows to save a PNG of the primary display. Both variants
are registered to support different keyboard layouts. Each capture gets a
timestamped filename. Press Ctrl+C in the terminal to stop the listener. If
another application already owns both hotkeys, the script reports the error.
