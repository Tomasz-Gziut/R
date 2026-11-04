# Screenshot hotkey

Install the dependency and start the listener:

```sh
py -m pip install -r requirements.txt
py screenshot.py
```

To build a standalone Windows executable, run `build_exe.bat`. It installs
PyInstaller if needed and creates `ScreenshotHotkey.exe` in the repository
root (and a copy in `dist\`). The one-file executable bundles the Python
runtime, this script, its imported dependencies, and the button template.
Run it and leave it open; it checks the screen every 10 seconds and saves
captures in `C:\Screenshots`.

Each capture gets a timestamped filename, then searches only the expected
button area for the **ZAGRAJ PONOWNIE** image in `assets\replay_button.png`.
The console prints `True` or `False`, then deletes the screenshot in either
case. When matched, the cursor moves to the button center and left-clicks it.
Press Ctrl+C in the terminal to stop the process.
