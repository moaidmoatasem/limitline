# Notes for contributors and coding agents

Limitline is a single-file, stdlib-only (Python 3.8+, tkinter) desktop widget for Claude Code usage. Unofficial; never put "Claude" in the product name.

## Layout
- `limitline.py`: the whole app. Sections, in order: config → log parsing (`LogStore`) → live limits (status-line bridge `--statusline`, opt-in saved-login `LiveLimits.fetch_oauth`) → alert rules (`plan_alerts`, pure) → aggregation (`build_snapshot`) → UI (`App`, `SettingsDialog`, `Mascot`) → `run_selftest` → `main`.
- `tests/test_core.py`: run `python tests/test_core.py`; must end with `FAILURES: none`.
- `docs/`: install, configuration, how it works, privacy, troubleshooting, premortem, roadmap.
- `scripts/install.ps1`, `scripts/install.sh`, `install.bat`: installers. The installed copy lives in `%LOCALAPPDATA%\Limitline\limitline.py` (Windows), and the Start-menu shortcut runs it with `pythonw.exe`.

## Rules
- Stdlib only. Keep Python 3.8 compatible.
- Never send, log or store message text or tokens. The status-line bridge stores only `rate_limits`.
- Don't make the saved-login (OAuth) path the default; it's opt-in because of Anthropic's terms.
- Bump `VERSION` in `limitline.py` and `pyproject.toml` together; add a CHANGELOG entry.
- Before a PR: `python tests/test_core.py` and, with a display, `python limitline.py --selftest`.

## Runtime files (in the user's home folder)
`.limitline.json` (settings, reloaded live when edited), `.limitline-live.json` (status-line data), `.limitline-logcheck.json` (log structure, no content), `.limitline-login-check.json` (last opt-in login status), `.limitline-statusline-note.txt` (last status-line problem).

Replacing the installed `limitline.py` makes a running copy restart itself on the new code.
