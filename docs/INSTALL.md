# Installation

## Requirements
- Python 3.8 or newer **with tkinter**
  - Windows / macOS (python.org installer): included.
  - Debian/Ubuntu: `sudo apt install python3-tk`
  - Fedora: `sudo dnf install python3-tkinter`
  - macOS with Homebrew Python: `brew install python-tk`
- Claude Code used on this computer (so there are logs to read). For live plan limits, be logged in to Claude Code.

## Just run it
```bash
git clone https://github.com/<you>/limitline.git
cd limitline
python limitline.py
```

## Install a launcher

### macOS / Linux
```bash
./scripts/install.sh
limitline            # add ~/.local/bin to PATH if needed
```
Copies the app to `~/.local/share/limitline`, creates `~/.local/bin/limitline` and, on Linux, an application-menu entry. Remove with `./scripts/install.sh --uninstall`.

### Windows
```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```
Copies the app to `%LOCALAPPDATA%\Limitline` and adds a Start-menu shortcut that uses `pythonw` (no console window). Remove with `-Uninstall`.

## Check your install
```bash
python limitline.py --selftest
```
Windows users: also follow [WINDOWS_TEST.md](WINDOWS_TEST.md).

## Connect live limits (recommended)
```bash
python limitline.py --install-statusline     # or Settings > Connect
```
This sets Claude Code's `statusLine` to call this app, keeping any existing status line running, and backs up what was there. Undo any time with `--uninstall-statusline`. Then send one message in Claude Code and the limits appear.

## Start at login
Open the app, press `S`, switch on **Launch at login**. It writes a startup entry (Windows: a `.vbs` in the Startup folder, macOS: a LaunchAgent, Linux: an autostart `.desktop` file) pointing at the script's current location, and removes it when switched off. Install the app to a permanent folder first (see above) so the entry doesn't break if you move the repo.

## Second account
```bash
python limitline.py --config-dir ~/.claude-work
```
Uses that folder's logs and login, a separate settings file, and may run alongside the main copy.
