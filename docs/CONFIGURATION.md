# Configuration

Edit in the app (`S`) or by hand in `~/.limitline.json` while the app is closed. Unknown keys are ignored; invalid values fall back to defaults. A file that can't be parsed is moved aside to `~/.limitline.json.bad` and the app says so once, instead of silently overwriting it. `--reset` clears everything.

| Key | Default | Meaning |
|---|---|---|
| `theme` | `dark` | `dark` or `light` |
| `accent` | `gold` | `gold`, `claude`, `ocean`, `forest`, `violet` |
| `opacity` | `0.97` | 0.4 to 1.0 |
| `topmost` | `true` | Keep above other windows |
| `frameless` | `true` (false on macOS) | Custom title bar |
| `mini` | `false` | Start as the pill |
| `tab` | `overview` | `overview`, `history`, `projects`, `sessions` |
| `metric` | `cost` | Gauge unit when live limits are unavailable: `cost`, `tokens`, `io` |
| `limit_mode` | `auto` | `auto` = your busiest past 5-hour window; `custom` = `limit_value` |
| `limit_value` | `0` | Custom limit ($ for cost, otherwise tokens) |
| `refresh_sec` | `15` | Local rescan interval (5 to 600) |
| `history_days` | `180` | Days of history kept in view (7 to 180). Long by default so older projects and months still show |
| `hist_range` | `30` | History chart span in days: `7`, `30`, `90` or `180` |
| `hist_mode` | `day` | History chart shape: `day` (columns) or `cum` (running total) |
| `scope` | `both` | Overview data scope: `local` (this PC's Claude Code only), `all` (account-wide only) or `both`. Affects display only - alerts always run from the full data |
| `proj_range` | `30d` | Projects span: `today`, `7d`, `30d`, `90d` or `180d` |
| `live_limits` | `true` | Show live plan limits (status-line file; needs Connect) |
| `live_oauth` | `false` | Advanced and risky: also use Claude Code's saved login token. See the README's Terms and risk section |
| `live_refresh` | `false` | With `live_oauth`: when the saved login has expired or been rejected, run `claude update` (the native CLI on PATH) once an hour to renew it, then retry once. Still opt-in |
| `live_interval_sec` | `120` | Base poll interval; faster while Claude is used, slower with stale logs, aligned to resets, and at most every 15 minutes when the keyboard has been idle that long (Windows) |
| `alerts` | `true` | Enable alerts |
| `alert_levels` | `[75, 90]` | Percent thresholds for the 5-hour window |
| `alert_levels_week` | `[50, 75, 90]` | Thresholds for the weekly limits |
| `alert_extra_spend` | `[]` | Extra-usage spend thresholds (e.g. `[50, 100, 150]`), in the feed's reported units; one alert per threshold per calendar month. Empty = off. The only alert that works when extra usage has no monthly cap |
| `alert_step` | `0` | Also alert every N% (e.g. `25` gives 25, 50, 75, 100). 0 or empty = off |
| `alert_forecast` | `true` | Pace warning: you're on course to hit the limit before the window resets |
| `alerts_pace_bypass` | `0` | With `alerts_pace_only`: levels at or above this % still alert when behind pace (0 = off) |
| `quiet_enabled` | `false` | Quiet hours: banner only - no flash, sound, notification, mascot or hook command |
| `quiet_from` / `quiet_to` | `"22:00"` / `"08:00"` | Quiet hours (24-hour, may wrap past midnight) |
| `snooze_until` | `0` | Set from the right-click menu (Snooze alerts) |
| `alert_sound` | `false` | System beep on alerts |
| `mascot` | `"subtle"` | `off`, `subtle` (75%+, pace warnings, resets) or `full` (every alert) |
| `mascot_animate` | `true` | Animate the mascot; off automatically when the OS reduces motion |
| `tray` | `false` | System-tray icon (needs the optional packages: `pip install "limitline[tray]"`). Click the icon to show/hide the widget |
| `tray_style` | `"ring"` | Tray icon look: `ring` (gauge arc) or `dot` (plain status dot) |
| `tray_fields` | `["window", "week"]` | What the tray hover text and title show: any of `window` (5-hour), `week`, `spend` |
| `quick_action_command` | `""` | Shell command or argv list in the tray menu's "Run quick action"; runs even when the widget is hidden |
| `alerts_pace_only` | `false` | Alert only when usage is ahead of the clock |
| `desktop_notify` | `true` | OS notifications |
| `notify_reset` | `true` | Notify when a nearly-full window resets |
| `on_alert_command` | `""` | Run on each alert (threshold, spend and pace warnings; silent during quiet hours and snoozes) |
| `on_threshold_command` | `""` | Like `on_alert_command` but never for pace warnings |
| `on_forecast_command` | `""` | Only for pace warnings |
| `on_reset_command` | `""` | Run on reset (silent during quiet hours and snoozes) |
| `on_start_command` | `""` | Run once when the app starts (runs even in quiet hours) |
| `extra_paths` | `[]` | Additional log folders |
| `price_overrides` | `{}` | Per-family prices, see below |

Config-file-only keys (no Settings row):

| Key | Example | Meaning |
|---|---|---|
| `alert_levels_week_<variant>` | `"alert_levels_week_opus": [25, 60]` | Alert levels for one weekly limit only (`opus`, `sonnet`, `fable_5`, ... - the model part of the bar's key). Anything without its own list keeps `alert_levels_week` |

## Price overrides
Costs use Anthropic's published API prices. Override a family if prices change:
```json
"price_overrides": { "opus": [5, 6.25, 10, 0.5, 25] }
```
Order: `[input, cache write 5m, cache write 1h, cache read, output]`, USD per million tokens. Families: `opus`, `sonnet`, `haiku`, `fable`.

## Hooks
The `on_*_command` settings run through the shell (or as an argv list - see below) with these environment variables. Alert-related hooks stay silent during quiet hours and while alerts are snoozed (the banner still shows). `on_start_command` runs once at launch with `LIMITLINE_EVENT=start` regardless of quiet hours:

| Variable | Example |
|---|---|
| `LIMITLINE_EVENT` | `threshold`, `spend`, `forecast`, `reset` or `start` |
| `LIMITLINE_LABEL` | `Week · Opus` |
| `LIMITLINE_PCT` | `90` (empty for spend alerts without a percentage) |
| `LIMITLINE_VERSION` | `2.5.0` |
| `LIMITLINE_UTILIZATION_<KEY>` | `LIMITLINE_UTILIZATION_SEVEN_DAY_OPUS=64` - one per live limit (5-hour, weekly, per-model, ...); unknown values are omitted |
| `LIMITLINE_RESETS_AT_<KEY>` | `LIMITLINE_RESETS_AT_SEVEN_DAY=2026-10-12T09:00` - ISO local time, omitted when unknown |
| `LIMITLINE_EXTRA_USED` / `LIMITLINE_EXTRA_LIMIT` | Extra-usage spend; the limit is omitted when uncapped |

Example: `curl -s -d "$LIMITLINE_LABEL at $LIMITLINE_PCT%" https://ntfy.sh/my-topic`

A command can also be an argv list (no shell involved, so no quoting worries), written as a JSON array either in the file (`"on_alert_command": ["py", "C:/hooks/limitline_alert.py"]`) or directly in the Settings entry. Each hook row's Test button runs the command with a sample `LIMITLINE_EVENT=test` environment and shows the exit code and output.
