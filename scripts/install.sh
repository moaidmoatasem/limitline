#!/usr/bin/env bash
# Installs Limitline for the current user on macOS or Linux.
#   ./scripts/install.sh            install + create launcher
#   ./scripts/install.sh --uninstall
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dest="${XDG_DATA_HOME:-$HOME/.local/share}/limitline"
bin="$HOME/.local/bin"
desktop="${XDG_DATA_HOME:-$HOME/.local/share}/applications/limitline.desktop"

if [ "${1:-}" = "--uninstall" ]; then
  rm -rf "$dest" "$bin/limitline" "$desktop"
  echo "Removed. Settings file ~/.limitline.json was kept."
  exit 0
fi

py="$(command -v python3 || true)"
[ -n "$py" ] || { echo "Python 3.8+ is required."; exit 1; }
"$py" -c "import tkinter" 2>/dev/null || {
  echo "Python's tkinter is missing."
  echo "  Debian/Ubuntu: sudo apt install python3-tk"
  echo "  Fedora:        sudo dnf install python3-tkinter"
  echo "  macOS:         brew install python-tk"
  exit 1
}

mkdir -p "$dest" "$bin"
install -m 644 "$here/limitline.py" "$dest/limitline.py"
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
Comment=Floating monitor for Claude Code usage
Exec=$bin/limitline
Terminal=false
Categories=Utility;
ENTRY
fi

echo "Installed to $dest"
echo "Run it with:  limitline        (preview: limitline --demo)"
case ":$PATH:" in *":$bin:"*) ;; *) echo "Note: add $bin to your PATH.";; esac
echo "Start at login: open the app > Settings (S) > Launch at login."
