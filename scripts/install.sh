#!/usr/bin/env bash
# Limitline installer for macOS and Linux (current user, no sudo).
#   ./scripts/install.sh            install, connect live limits, start at login, launch
#   ./scripts/install.sh --uninstall
#   curl -fsSL https://raw.githubusercontent.com/<you>/limitline/main/scripts/install.sh | bash
# Options: --no-autostart  --no-launch
set -euo pipefail
REPO="${LIMITLINE_REPO:-moaidmoatasem/limitline}"
dest="${XDG_DATA_HOME:-$HOME/.local/share}/limitline"
bin="$HOME/.local/bin"
desktop="${XDG_DATA_HOME:-$HOME/.local/share}/applications/limitline.desktop"
autostart=1; launch=1; uninstall=0
for a in "$@"; do case "$a" in
  --uninstall) uninstall=1;; --no-autostart) autostart=0;; --no-launch) launch=0;; esac; done

py="$(command -v python3 || true)"
if [ "$uninstall" = 1 ]; then
  if [ -n "$py" ] && [ -f "$dest/limitline.py" ]; then
    "$py" "$dest/limitline.py" --uninstall-statusline || true
    "$py" "$dest/limitline.py" --autostart off || true
  fi
  rm -rf "$dest" "$bin/limitline" "$desktop"
  echo "Removed Limitline, its launcher, startup entry and status-line hook. Settings (~/.limitline.json) were kept."
  exit 0
fi

[ -n "$py" ] || { echo "Python 3.8+ is required (macOS: brew install python-tk; Debian/Ubuntu: sudo apt install python3 python3-tk)."; exit 1; }
"$py" -c "import tkinter" 2>/dev/null || {
  echo "Python's tkinter is missing:"
  echo "  Debian/Ubuntu: sudo apt install python3-tk"
  echo "  Fedora:        sudo dnf install python3-tkinter"
  echo "  macOS:         brew install python-tk"
  exit 1
}

mkdir -p "$dest" "$bin"
here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." 2>/dev/null && pwd || true)"
if [ -n "$here" ] && [ -f "$here/limitline.py" ]; then
  install -m 644 "$here/limitline.py" "$dest/limitline.py"
else
  echo "Downloading Limitline..."
  curl -fsSL "https://raw.githubusercontent.com/$REPO/main/limitline.py" -o "$dest/limitline.py"
fi
cat > "$bin/limitline" <<LAUNCH
#!/usr/bin/env bash
exec "$py" "$dest/limitline.py" "\$@"
LAUNCH
chmod +x "$bin/limitline"

if [ "$(uname)" = "Linux" ]; then
  mkdir -p "$(dirname "$desktop")"
  cat > "$desktop" <<ENTRY
[Desktop Entry]
Type=Application
Name=Limitline
Comment=Floating monitor for Claude Code usage (unofficial)
Exec=$bin/limitline
Terminal=false
Categories=Utility;
ENTRY
fi

"$py" "$dest/limitline.py" --install-statusline || true
[ "$autostart" = 1 ] && "$py" "$dest/limitline.py" --autostart on || true

echo ""
echo "Installed. Run:  limitline      (check this computer: limitline --selftest)"
case ":$PATH:" in *":$bin:"*) ;; *) echo "Note: add $bin to your PATH.";; esac
if [ "$launch" = 1 ]; then nohup "$py" "$dest/limitline.py" >/dev/null 2>&1 & fi
