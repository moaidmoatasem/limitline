# How it works

## Scope and window
Everything except the live percentages comes from **this computer's Claude Code logs**. claude.ai chat, the desktop app and cloud (web) Claude Code runs write no local files, so they cannot appear as costs or projects - but the live plan percentages are Anthropic's account-wide numbers and do include them.

The History window defaults to **180 days** (`history_days`, 7-180) so older projects still show. Entries are kept by their message timestamp, so a project last used months ago still counts until it ages past the window. The History and Projects tabs offer their own ranges (up to 180 days); the daily chart draws **weekly** bars at 90+ days, and the weekday x hour heatmap covers the selected range.

Projects are named after the session's working directory: a session inside a Claude Code worktree (`<repo>/.claude/worktrees/...`) counts as the repo, and a session opened in a nested subfolder (two generic folders deep, like `ui/src`) keeps the project under the user's home directory.

## Local logs
Claude Code writes one JSONL file per session under `~/.claude/projects` (also `~/.config/claude/projects`, or `$CLAUDE_CONFIG_DIR`). The app reads them incrementally in a background thread: it remembers a byte offset per file, ignores a partial last line, and re-reads a file only if it shrinks or if a read failed (a locked or vanished file is retried on the next scan instead of being remembered as read).

Each assistant message can be logged several times while streaming. Entries are de-duplicated by `(message.id, requestId)` keeping the largest `output_tokens`.

## Cost
Per message: input, output, cache writes (5-minute and 1-hour priced separately when the log says which), and cache reads, at the model's per-million-token price. Fast mode (x2), US-only inference (x1.1) and web searches ($0.01 each) are applied. If a log line carries `costUSD`, that value wins. These are API-equivalent estimates.

## 5-hour windows
A window starts at the top of the hour of the first message and lasts 5 hours; if the next message arrives after the window ended, a new one starts. When live data is available, its reset time defines the window instead.

## Live plan limits
Claude Code documents a [status line](https://code.claude.com/docs/en/statusline): a command you configure that receives JSON on stdin, including `rate_limits.five_hour` and `rate_limits.seven_day` (`used_percentage`, `resets_at`) for Pro and Max subscribers, after the first response of a session. `--install-statusline` points that setting at this app (`--statusline` mode), which saves only the `rate_limits` block to `~/.limitline-live.json` and prints a short line (or runs your previous status-line command, which is kept via `--then`). The window reads that file every few seconds. No login or token is involved. Limitation: values only update while Claude Code is running, and the status-line feed normally carries only the 5-hour and weekly windows (per-model weekly limits come with the optional login mode below).

Advanced, off by default: with `live_oauth` on, if no status-line data exists the app reads Claude Code's saved OAuth token and calls `https://api.anthropic.com/api/oauth/usage` (no redirects are followed, the token is never sent anywhere else). From the same host it also fetches the account's email and any prepaid-credit balance (`/api/oauth/profile`, `/api/oauth/organizations/{org}/prepaid/credits`); the email is memoized per token, the org uuid must look like a real uuid before the prepaid request goes out, the balance is refetched at most every 30 minutes, and any failure just hides the line - both values stay in memory and are never saved. An expired or rejected login says "open Claude Code once to refresh it" unless you switch on `live_refresh`, which runs `claude update` (the native CLI on PATH only) at most once an hour and retries once with the re-read credentials. That endpoint is undocumented and Anthropic's terms restrict third-party use of the token; see the README.

## Gauge fallback
Without live data the ring shows window usage against your busiest past window (or a custom limit), so it is a relative indicator, not your real quota.

## App icon
The window/taskbar icon is a gauge-ring mark drawn by the same dependency-free rasteriser as the tray icon, tinted to the current accent and theme, and set with `iconphoto` - so there is no bundled image and no new package. The rasteriser outputs RGBA, which a small `zlib`-based PNG encoder turns into a `PhotoImage`; the same encoder builds a multi-size `limitline.ico` kept next to the app for the Start-menu/desktop shortcuts (the installer points them at it; `--write-icon PATH` writes it on demand). The `.ico` is refreshed on launch and whenever the accent changes, and a failure is always silent.

## Checking itself against Claude Code
Claude Code writes its own running cost total (`cost-state`) into the session log. The app compares it with the cost it computed from the log *up to that same point* and reports the match. Whenever Claude Code's record is at least as fresh as the log, both exact figures are shown side by side - `$0.275273 (Claude Code) · $0.275273 (logs) · 100% match` in the footer (which alternates with the plain coverage percentage) and the exact dollars on the session row. In the sessions we verified, the totals agreed to the cent. Comparing against the whole, still-growing log would be wrong, which an earlier version of this app did.
