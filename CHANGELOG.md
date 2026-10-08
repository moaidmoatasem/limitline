# Changelog

## 2.8.0
- **The app now has its own icon.** A gauge-ring mark, drawn with the same dependency-free rasteriser as the tray icon and tinted to follow the accent setting (and dark/light theme), sets the window and taskbar icon instead of the generic Python/Tk one. No image files or new packages: the icon is rasterised in pure Python and encoded to PNG/ICO with only `zlib`/`struct`. A multi-size `limitline.ico` is kept next to the app for the Start-menu/desktop shortcuts (the installer points them at it; new `--write-icon PATH` writes it on demand), refreshed on each launch and whenever the accent changes.
- Tests: PNG/ICO structure, icon geometry (transparent rounded corners, opaque centre, accent arc present with the expected sweep).

## 2.7.0
- **Saved-login mode now shows your account email and prepaid balance.** With "Use saved login instead" on, the limits card and Settings status line also show the account's email and any prepaid credits left (normalized from the minor-unit balance, currency included). Both live in memory only - never written to the settings file - and the prepaid request only goes out when extra usage is enabled, the org uuid passes validation, and at most every 30 minutes; any failure just hides the line, never shows an error.
- **Optional automatic login refresh (off by default).** With the saved login: a new "Auto-refresh expired login" switch (`live_refresh`) runs `claude update` (the native CLI on PATH only) when the saved login has expired or been rejected - at most once an hour, one retry with the re-read credentials, and never as the default path; without the switch, an expired login still says "open Claude Code once to refresh it" exactly as before.
- Ideas from usage-monitor-for-claude: `/api/oauth/profile` (email, validated org uuid) and `/api/oauth/organizations/{org}/prepaid/credits`, both memoized/cadence-gated; `claude update` as the single, opt-in refresh mechanism.
- Fix (found against live data): the `/usage` response also lists experiment code names (e.g. `nimbus_quill`) as quota objects with a utilization of 0 and no reset window. Those are no longer shown as phantom 0% limits; a real limit is kept when it has a reset window or a name we understand, so an unrecognized-but-active limit (like `iguana_necktie`, a $100 cap with a reset date) still appears. Also made the prepaid parser read `balance.credits` (the live payload returns `balance.money: null`) and fixed a zero-decimal currency (e.g. JPY) losing its decimal place.
- Tests: prepaid normalization/formatting, strict org-uuid regex, oauth headers, refresh gating (off by default, hourly rate limit), profile memoization per token, prepaid 30-minute cadence and invalid-org rejection, failing profile/prepaid never breaking the usage fetch, expired token with refresh off staying "expired", email/prepaid not being settings keys.

## 2.6.0
- **System-tray icon (opt-in).** A gauge-ring icon in the tray showing the 5-hour percentage, with the week and spend figures in the hover text; click the icon to show/hide the widget, run an optional quick-action command, or quit. Off by default; needs the optional packages (`pip install "limitline[tray]"` or `pip install pystray Pillow`) - the app degrades gracefully without them and the Settings row says so. Tray style (`ring`/`dot`) and the shown figures (`tray_fields`: window/week/spend) are config-file keys. This was the last stdlib-only holdout: the core stays dependency-free, the tray is a guarded extra.
- Tests: tray tooltip/menu line formatting, config sanitization of the tray keys, availability probing.

## 2.5.0
- **Per-model alert thresholds.** A weekly limit can now have its own alert levels without touching the shared ones: set `alert_levels_week_opus` (or `_sonnet`, `_fable_5`, ...) in `~/.limitline.json` to override `alert_levels_week` for just that model; anything without its own list keeps the shared weekly levels. Config-file only, on purpose - no new settings rows.
- **Pace-only alerts can be bypassed at the top.** With "Only when ahead of pace" on, levels at or above a new `alerts_pace_bypass` value (0 = off, default) still alert even when usage is behind the clock - so a quiet week can't hide a 95% reading.
- **Sharper hook commands.** Three new optional commands next to "Run on alert": `on_threshold_command` (alerts only, never pace warnings), `on_forecast_command` (pace warnings only), plus the existing `on_alert_command` as the catch-all. Commands may now be argv lists (or a JSON-array string) instead of shell strings, so no shell quoting is needed.
- **Richer hook environment.** Hooks now also get `LIMITLINE_VERSION`, `LIMITLINE_UTILIZATION_<KEY>` and `LIMITLINE_RESETS_AT_<KEY>` for every live limit (unknown values are omitted, never blanked), and `LIMITLINE_EXTRA_USED` / `LIMITLINE_EXTRA_LIMIT` for extra usage. Still no tokens or message text, ever.
- **Test buttons.** Each hook row in Settings has a "Test" button that runs the command with a sample `LIMITLINE_EVENT=test` environment and reports the exit code and output - no more guessing why a hook didn't fire.
- Tests: per-variant fallback/override (including synthetic `limits[]` fields), pace bypass on/off, hook env omit-when-unknown, list/JSON-list commands, event routing, load-time sanitization of config-file-only keys.

## 2.4.0
- **The usage API's `limits[]` array is understood.** Newer responses carry per-model weekly limits only inside that array (scoped by model), no longer as top-level fields. Each active scoped limit now appears as its own bar (e.g. "Week · Fable 5"), named after the group's shared reset window; an inactive scoped limit shows at 0% so the limit is visible before first use, and an existing top-level field is never overwritten.
- **Unknown quota types stay visible.** A rate_limits key Limitline doesn't recognise (from a future Claude Code, or a new quota type) is kept with a generated label and ordered last, instead of silently disappearing - from the status-line file as well as the login feed.
- **Hardened saved-login fetch (opt-in mode).** A 429 now honours the server's Retry-After, and repeated failures back off exponentially (60s doubling to a 15-minute cap) instead of hammering; a certificate failure, an auth rejection and a server error each get their own status and message; error replies show Anthropic's own message (minus the redundant "please try again later" advice).
- **`--verbose` diagnostics.** Prints redacted operational lines to the console (home folder shortened to `~`; never tokens or message text) for setup problems and bug reports.
- Fix: the 429 "slow down" adjustment was computed and then immediately overwritten by the adaptive interval; the backoff now actually applies.
- Tests: `limits[]` merge (naming, 0% inactive, no overwrite, skipped unknown groups), unknown-key bridge survival with generated labels, Retry-After and server-message extraction, backoff schedule, currency passthrough, verbose redaction.

## 2.3.4
- **Your older projects now show.** The History window defaults to 180 days (was 30), the History and Projects range pickers now reach 180 days (both charts were capped at 30 days, so older data stayed hidden even after widening the window), the "When you use Claude" heatmap follows the selected range too (it was fixed at 30 days and rendered blank), and the 90/180-day charts draw weekly bars so 180 two-pixel columns don't blur into a wall. Nothing was ever lost - July-era sessions like the WSL ones were simply outside the old window.
- **Projects group correctly now.** A session opened inside a Claude Code worktree (`<repo>/.claude/worktrees/...`) counts as the repo it was made from, and a session opened in a nested subfolder (`repo/cherenkov/web/ui/src`) keeps the project's own name instead of showing `src`. One project no longer appears as four.
- **Scope is now labelled.** The plan-limits card says the percentages are Anthropic's account-wide numbers (web, desktop, cloud, other PCs), and the history footer and KPI card say they come from Claude Code logs on this computer. Per-model weekly windows (Opus/Sonnet/other apps) are read from whichever source has them, and ISO reset times are understood.
- **Ideas from usage-monitor-for-claude.** Extra-usage spend alerts (`alert_extra_spend`, off by default, one per threshold per calendar month - the only alert that works when extra usage has no monthly cap); hour dividers on the History 5-hour bars; a Claude Code install/version readout on the limits card (native CLI plus VS Code/Cursor extensions; WSL installs aren't visible from Windows); a run-once `on_start_command`; idle-aware polling (at most every 15 minutes when the keyboard is idle, resets still win); unknown future quota types get a NEW badge instead of silently appearing. Deliberately not adopted at the time: tray icon (arrived in 2.6.0 as an opt-in extra), automatic token refresh (arrived in 2.7.0, off by default), full translations (deferred).
- **Exact numbers where they matter.** Hover tooltips, the KPI cards and session rows show full-precision figures (`$0.275273`, `1,843,291` tokens) next to Claude Code's own billed total; the footer alternates between the exact side-by-side comparison ("Claude Code $0.275273 · logs $0.275273 · 100% match") and the coverage percentage. Percentages show a decimal only when it carries information (42% / 42.4%), `999999` tokens reads `1.00M`, and chart axes show sub-cent values as `$0.003` instead of `$0`.
- Fix: quiet hours and snoozes now silence the alert/reset hook commands too - banner only, exactly as the setting promises.
- Fix: a corrupt `~/.limitline.json` is moved aside to `.limitline.json.bad` and reported once, instead of being silently replaced by defaults on the next save.
- Fix: a log file that is locked or unreadable during a scan is retried on the next scan, instead of being remembered as already read.
- Fix: the status line speaks UTF-8 on Windows (stdin and stdout), so `·` no longer reaches Claude Code as `Â·`, non-ASCII input can't crash it, and `main` never lets an exception escape into Claude Code.
- Fix: status-line quoting now covers cmd.exe metacharacters (`& | < > ^ % ( )`) even without spaces, and Connect no longer mistakes another tool's `--statusline` for its own - a foreign status line is kept as the chain, never replaced.
- Fix: launch-at-login writes the Windows `.vbs` as UTF-16, so non-ASCII install paths work; the demo's weekly limit resets next Monday 09:00 even when the demo runs on a Monday; the stale-feed reason now shows on the limits card.
- Installers: PowerShell 5.1 no longer aborts on a native command's stderr (the friendly "no tkinter" message actually shows now), and both installers warn honestly when they couldn't remove the status-line hook.
- Tests: formatter edge cases, comparison snapshot, corrupt-config backup, locked-file retry, quiet-hook gating, shell-quoting round-trip, UTF-8 status-line bytes; worktree/subfolder project naming, 180d window and range values, heatmap window, weekly bucket sums, spend/monthly alert rules, install probing, adaptive poll intervals, unknown quota ordering; `--selftest` gained matching checks. New `tests/test_render.py` verifies the real chart widgets draw the right bars at the right heights and lights the right heatmap cells (skips without a display).

## 2.3.1
- Fix: live limits never arrived on some Windows setups. The status line could be registered with `pythonw.exe` (no stdin/stdout, so Claude Code got nothing); it now always uses `python.exe` and forward-slash paths, and Connect repairs a stale registration in place. Problems are noted in `.limitline-statusline-note.txt`.

## 2.3
- **Alerts upgraded:** separate levels for the 5-hour window and weekly limits, optional "every N%" steps (25 → 50 → 75 → 100), a pace warning ("at this pace you'll run out at 15:40"), quiet hours, snooze from the right-click menu, optional sound. During quiet hours or a snooze the banner still shows; flash, sound, notification and mascot stay silent.
- **Mascot "Tick":** an original animated gauge character appears beside the widget when an alert fires, with a mood for each level (calm → worried → alarmed → out, joyful on reset). Off / Subtle / Every alert; stops animating when the OS asks to reduce motion; click to dismiss.
- Alert rules are now a tested pure function; selftest checks the mascot.

## 2.2
- **Easier setup:** first-run welcome window (history found, one-click Connect, start with computer); a Connect button right on the limits card; `install.bat` / `install.sh` that install Python if needed, add a launcher, connect, autostart and launch, with clean `--uninstall`; `pip` / `pipx` install (`limitline`, `limitline-gui`); `--setup`, `--autostart on|off`.
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
