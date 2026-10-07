# Troubleshooting

**`No module named tkinter`**: install it, see [INSTALL.md](INSTALL.md).

**Window is empty / "no data"**: Claude Code has not written logs yet, or they are elsewhere. Add the folder in Settings (extra paths) or use `--path DIR`.

**No live limits / "Not connected yet"**: run `python limitline.py --install-statusline` (or Settings > Connect), then send a message in Claude Code. Limits only exist for Pro/Max accounts and appear after the first response of a session. If you already had a status line it keeps working. Undo with `--uninstall-statusline`.

**Percent looks old**: Claude Code only reports while it is open; the card shows the age.

**Percent differs from `/usage`**: the status-line feed is Claude Code's own; small timing differences are normal. Without live data the ring is relative to your busiest window.

**Costs lower than Claude Code reports**: expected; the logs undercount. See HOW_IT_WORKS.

**"Already running"**: another copy holds the port. Use `--multi`, or `--config-dir` for a second account.

**Console window on Windows**: start with `pythonw` or the Start-menu shortcut.

**Window off-screen after a monitor change**: delete `x` and `y` from `~/.limitline.json`, or run with `--reset`.
