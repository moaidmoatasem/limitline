# Installation

## Fastest
- **Windows:** double-click `install.bat` (or `powershell -ExecutionPolicy Bypass -File scripts\install.ps1`). Options: `-NoAutostart`, `-NoLaunch`, `-Desktop` (desktop shortcut), `-Uninstall`.
- **macOS / Linux:** `./scripts/install.sh` (options `--no-autostart`, `--no-launch`, `--uninstall`).
- **pipx / pip:** `pipx install git+https://github.com/<you>/limitline`, then `limitline` (GUI without a console on Windows: `limitline-gui`).

The installers: make sure Python 3.8+ with tkinter exists (Windows installs it with winget if missing), copy the app to a permanent folder, add a launcher, connect live limits through Claude Code's status line (your existing one keeps working), turn on launch at login, and start the app. All per-user, no admin rights.

One-liners once the repo is public (replace `<you>`):
```powershell
irm https://raw.githubusercontent.com/<you>/limitline/main/scripts/install.ps1 | iex
```
```bash
curl -fsSL https://raw.githubusercontent.com/<you>/limitline/main/scripts/install.sh | bash
```
Read a script before piping it to a shell.

## Requirements
Python 3.8+ with tkinter. Windows/macOS python.org installers include it. Debian/Ubuntu `sudo apt install python3-tk`; Fedora `sudo dnf install python3-tkinter`; Homebrew `brew install python-tk`.

## First run
The welcome window offers three buttons: see which Claude Code history was found, **Connect** live limits, and start with your computer. Reopen it any time with `limitline --setup`. Everything else is in Settings (press `S`).

## Manual steps (if you prefer)
- Live limits: `limitline --install-statusline` (undo `--uninstall-statusline`), then send a message in Claude Code.
- Launch at login: `limitline --autostart on|off`.
- Check this computer: `limitline --selftest` (Windows: also [WINDOWS_TEST.md](WINDOWS_TEST.md)).
- Second account: `limitline --config-dir ~/.claude-work`.

## Update
Re-run the installer or `pipx upgrade limitline`. Settings are kept.
