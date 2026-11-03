# Fortnite monitor

Run with:

```sh
python loop.py
```

On Windows, the script checks every five seconds whether Fortnite is installed
and running. It reads Fortnite's install location from the Epic Games Launcher
manifest, then asks Epic Games Launcher to start Fortnite when it is not
running. Using the launcher ensures Fortnite starts with the required launch
parameters. The script does not install the game.

Press **Ctrl+Q anywhere on the computer** to close Fortnite and stop the
monitor, or use Ctrl+C in the terminal to stop only the monitor. Ctrl+Q
force-closes Fortnite. If another application already owns Ctrl+Q as a global
hotkey, the script will report that it could not register it.
