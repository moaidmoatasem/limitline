# Privacy

- Reads only usage metadata (token counts, model, timestamps, working-directory name) from Claude Code's local logs. Message text is not displayed or stored.
- Settings are saved to `~/.limitline.json`. Nothing else is written, except CSV files you export and the optional login-startup entry.
- Network: by default **none**. Live limits come from a local file written by Claude Code's status-line hook (only the `rate_limits` block is kept). The advanced `live_oauth` mode, off by default, additionally reads Claude Code's saved login token and contacts `api.anthropic.com` only (redirects are never followed). In that mode it also fetches your account email and any prepaid balance from the same host; both are kept in memory only, never written to the settings file, and the prepaid request is skipped (line hidden) on any failure. `live_refresh`, also off by default, runs `claude update` locally - it contacts no extra host.
- A tiny local socket on `127.0.0.1:47613` prevents two copies from running. It accepts no data.
- The optional tray icon (off by default, needs `pystray` + `Pillow`) is drawn locally from the same snapshot the widget shows; it sends nothing anywhere.
- Alert hooks run only the command you configured.
