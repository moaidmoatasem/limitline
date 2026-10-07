# Changelog

## 2.2
- **Renamed to Limitline** (neutral name, "unofficial" notice) to follow Anthropic's trademark rules. Settings migrate from `~/.claude-usage-popup.json`; hook variables are now `LIMITLINE_EVENT/LABEL/PCT`; if you connected the old build's status line, run `--install-statusline` again.
- `--selftest`: end-to-end check of a computer (window rendering, DPI, fonts, status-line with shell quoting, startup entry, notification).
- Settings window scrolls on short screens, with Save/Cancel pinned.
- **Live limits now come from Claude Code's official status line** (no login or token access). `--install-statusline` / Settings > Connect, with backup, chaining of an existing status line, and exact undo.
- The saved-login method is opt-in (`live_oauth`, off by default) with a warning, and never follows redirects.
- Fixed the log-vs-Claude-Code cost comparison (it used a stale snapshot against the full log); it is now like-for-like.
- Footer flags models missing from the price table.
- Docs: premortem with audit results and critique, terms-and-risk section, updated install/privacy/troubleshooting.

## 2.1
- Refined look: obsidian palette with a champagne-gold accent, rounded cards, light display numerals where the system has them.
- Every icon, bar, toggle, slider, badge and corner is now anti-aliased (drawn by a built-in vector rasteriser) instead of jagged canvas lines.
- Pushpin, refresh and settings icons redrawn; softer status dot; better button contrast on light accents.

## 2.0
- Live plan limits (session, weekly, per-model, extra usage) from the login Claude Code already saved.
- Elapsed-time markers and "ahead of pace" warnings on limit bars; burn rate, projection and limit ETA.
- Four tabs (Overview, History, Projects, Sessions), hourly/daily charts by model, weekday x hour heatmap.
- Mini pill mode, themes, accents, opacity, always-on-top, launch at login.
- Alerts (banner, border flash, desktop notification), pace-only alerts, command hooks.
- Multi-account via `--config-dir`, CSV export, single-instance lock, `--demo` mode.
- Coverage note comparing log-derived cost with Claude Code's own cost record.

## 1.0
- First popup: 5-hour block tokens, today and 7-day totals.
