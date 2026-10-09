# Troubleshooting

**`No module named tkinter`**: install it, see [INSTALL.md](INSTALL.md).

**Window is empty / "no data"**: Claude Code has not written logs yet, or they are elsewhere. Add the folder in Settings (extra paths) or use `--path DIR`.

**Ring/limits show high usage but the History or Projects tabs are empty**: that's expected. The ring and plan bars are Anthropic's account-wide numbers (they include claude.ai, the desktop app, cloud and other PCs); the log tabs only cover this computer's Claude Code. If the tabs are *older* but not empty, use the "Show …" button that appears on an empty range to widen it to your newest activity.

**No live limits / "Not connected yet"**: run `python limitline.py --install-statusline` (or Settings > Connect), then send a message in Claude Code. Limits only exist for Pro/Max accounts and appear after the first response of a session. If you already had a status line it keeps working. Undo with `--uninstall-statusline`.

**Percent looks old**: Claude Code only reports while it is open; the card shows the age.

**Percent differs from `/usage`**: the status-line feed is Claude Code's own; small timing differences are normal. Without live data the ring is relative to your busiest window.

**Costs differ from Claude Code**: the footer compares them like-for-like - Claude Code's exact dollars next to what the logs account for, with the match percentage. Small differences (background Haiku calls Claude Code bills but the logs miss) are normal; if the numbers look wrong, see HOW_IT_WORKS.

**Settings file ignored / "couldn't be read"**: `~/.limitline.json` was corrupt; it was moved to `~/.limitline.json.bad` and defaults are in use. Fix the copy if you want your old settings back.

**Claude Code shows a status-line error**: a hook from an old install may be left. Delete the `statusLine` entry from `~/.claude/settings.json`, or run `--uninstall-statusline` from a fresh copy. Details of the last problem are in `~/.limitline-statusline-note.txt`.

**"Already running"**: another copy holds the port. Use `--multi`, or `--config-dir` for a second account.

**Console window on Windows**: start with `pythonw` or the Start-menu shortcut.

**Window off-screen after a monitor change**: delete `x` and `y` from `~/.limitline.json`, or run with `--reset`.

**Push alerts to your phone**: set a hook command that posts to [ntfy](https://ntfy.sh) (install the ntfy app, pick a private topic name): `curl -s -d "$LIMITLINE_LABEL at $LIMITLINE_PCT%" https://ntfy.sh/my-secret-topic`. Use `on_alert_command` for limit alerts or `on_start_command` to confirm the app launched.

**Logs come from WSL / another machine**: the limits card shows which Claude Code installs were found on this computer (native CLI, VS Code / Cursor extensions). WSL installs aren't visible from Windows, so sessions synced in from WSL still count as history but can't feed live data - connect the status line (or the saved login) in the environment where Claude Code actually runs.
