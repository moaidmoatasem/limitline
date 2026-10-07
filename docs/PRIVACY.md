# Privacy

- Reads only usage metadata (token counts, model, timestamps, working-directory name) from Claude Code's local logs. Message text is not displayed or stored.
- Settings are saved to `~/.limitline.json`. Nothing else is written, except CSV files you export and the optional login-startup entry.
- Network: by default **none**. Live limits come from a local file written by Claude Code's status-line hook (only the `rate_limits` block is kept). The advanced `live_oauth` mode, off by default, additionally reads Claude Code's saved login token and contacts `api.anthropic.com` only (redirects are never followed).
- A tiny local socket on `127.0.0.1:47613` prevents two copies from running. It accepts no data.
- Alert hooks run only the command you configured.
