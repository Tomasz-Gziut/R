# Fortnite monitor

Run with:

```sh
python loop.py
```

On Windows, the script checks every five seconds whether Fortnite is installed
and running. It reads Fortnite's install location and launch executable from
the Epic Games Launcher manifest, then starts that executable when Fortnite is
not running. If the manifest does not provide an executable, it asks Epic Games
Launcher to start Fortnite instead. The script does not install the game.

Press **Ctrl+Q anywhere on the computer** to quit, or use Ctrl+C in the terminal.
If another application already owns Ctrl+Q as a global hotkey, the script will
report that it could not register it.
