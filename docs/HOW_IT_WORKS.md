# How it works

## Local logs
Claude Code writes one JSONL file per session under `~/.claude/projects` (also `~/.config/claude/projects`, or `$CLAUDE_CONFIG_DIR`). The app reads them incrementally in a background thread: it remembers a byte offset per file, ignores a partial last line, and re-reads a file only if it shrinks.

Each assistant message can be logged several times while streaming. Entries are de-duplicated by `(message.id, requestId)` keeping the largest `output_tokens`.

## Cost
Per message: input, output, cache writes (5-minute and 1-hour priced separately when the log says which), and cache reads, at the model's per-million-token price. Fast mode (x2), US-only inference (x1.1) and web searches ($0.01 each) are applied. If a log line carries `costUSD`, that value wins. These are API-equivalent estimates.

## 5-hour windows
A window starts at the top of the hour of the first message and lasts 5 hours; if the next message arrives after the window ended, a new one starts. When live data is available, its reset time defines the window instead.

## Live plan limits
Claude Code documents a [status line](https://code.claude.com/docs/en/statusline): a command you configure that receives JSON on stdin, including `rate_limits.five_hour` and `rate_limits.seven_day` (`used_percentage`, `resets_at`) for Pro and Max subscribers, after the first response of a session. `--install-statusline` points that setting at this app (`--statusline` mode), which saves only the `rate_limits` block to `~/.limitline-live.json` and prints a short line (or runs your previous status-line command, which is kept via `--then`). The window reads that file every few seconds. No login or token is involved. Limitation: values only update while Claude Code is running, and per-model weekly limits are not included.

Advanced, off by default: with `live_oauth` on, if no status-line data exists the app reads Claude Code's saved OAuth token and calls `https://api.anthropic.com/api/oauth/usage` (no redirects are followed, the token is never sent anywhere else). That endpoint is undocumented and Anthropic's terms restrict third-party use of the token; see the README.

## Gauge fallback
Without live data the ring shows window usage against your busiest past window (or a custom limit), so it is a relative indicator, not your real quota.

## Checking itself against Claude Code
Claude Code writes its own running cost total (`cost-state`) into the session log. The app compares it with the cost it computed from the log *up to that same point* and reports the match. In the one session we verified, the totals agreed within about 1%, and the Opus 5.5 cost was identical to the cent. Remaining differences were small background (Haiku) calls and a few input tokens. Comparing against the whole, still-growing log would be wrong, which an earlier version of this app did.
