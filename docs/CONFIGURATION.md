# Configuration

Edit in the app (`S`) or by hand in `~/.limitline.json` while the app is closed. Unknown keys are ignored; invalid values fall back to defaults. `--reset` clears everything.

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
| `history_days` | `30` | Days of history kept in view (7 to 180) |
| `live_limits` | `true` | Show live plan limits (status-line file; needs Connect) |
| `live_oauth` | `false` | Advanced and risky: also use Claude Code's saved login token. See the README's Terms and risk section |
| `live_interval_sec` | `120` | Base poll interval; adapts to activity and resets |
| `alerts` | `true` | Enable alerts |
| `alert_levels` | `[75, 90]` | Percent thresholds |
| `alerts_pace_only` | `false` | Alert only when usage is ahead of the clock |
| `desktop_notify` | `true` | OS notifications |
| `notify_reset` | `true` | Notify when a nearly-full window resets |
| `on_alert_command` | `""` | Shell command run on each alert |
| `on_reset_command` | `""` | Shell command run on reset |
| `extra_paths` | `[]` | Additional log folders |
| `price_overrides` | `{}` | Per-family prices, see below |

## Price overrides
Costs use Anthropic's published API prices. Override a family if prices change:
```json
"price_overrides": { "opus": [5, 6.25, 10, 0.5, 25] }
```
Order: `[input, cache write 5m, cache write 1h, cache read, output]`, USD per million tokens. Families: `opus`, `sonnet`, `haiku`, `fable`.

## Hooks
`on_alert_command` and `on_reset_command` run through the shell with these environment variables:

| Variable | Example |
|---|---|
| `LIMITLINE_EVENT` | `alert` or `reset` |
| `LIMITLINE_LABEL` | `5-hour session` |
| `LIMITLINE_PCT` | `90` |

Example: `curl -s -d "$LIMITLINE_LABEL at $LIMITLINE_PCT%" https://ntfy.sh/my-topic`
