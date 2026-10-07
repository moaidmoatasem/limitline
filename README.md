# Limitline

> **Unofficial.** Limitline is an independent community project. It is not made, endorsed or sponsored by Anthropic. "Claude" and "Claude Code" are Anthropic's trademarks, used here only to say which tool it works with.

A small floating desktop window that keeps your **Claude Code** usage in view: how much of the current 5-hour window and the weekly limits you've used, when they reset, how fast you're burning, and where you'll land.

One Python file. No dependencies beyond the standard library (tkinter). Windows, macOS and Linux.

![Overview](docs/img/overview.png)

## Features

- **Live plan limits** from Claude Code's own documented status-line feature: your 5-hour and weekly percentages and reset times, with **no login or token access**. One-time connect: `python limitline.py --install-statusline` (or Settings > Connect). An opt-in advanced mode that uses the saved login is available but off by default, see [Terms and risk](#terms-and-risk).
- **Pace awareness**: a white marker on each limit bar shows how much of the period has elapsed; the bar changes to "Ahead of pace" when you're using it faster than the clock. Burn rate ($/h, tokens/min), projection at reset, and an ETA to the limit.
- **Four tabs**: Overview (ring gauge, today / 7d / 30d, last 24 hours by model), History (daily chart, weekday x hour heatmap, recent 5-hour windows), Projects, Sessions.
- **Alerts**: banner, border flash and desktop notification at thresholds you pick (default 75% and 90%), a heads-up when a full window resets, optional pace-only mode, and shell-command hooks.
- **Mini pill** mode, dark and light themes, accents, opacity, always-on-top, launch at login.
- **Multi-account**: run several copies with `--config-dir`.
- **CSV export**, single-instance lock, `--demo` mode with sample data.

| History | Sessions |
|---|---|
| ![History](docs/img/history.png) | ![Sessions](docs/img/sessions.png) |

## Install (about a minute)

| You have | Do this |
|---|---|
| **Windows** | Download the repo, double-click **`install.bat`**. It installs Python 3.12 via winget if missing, adds a Start-menu shortcut, connects live limits, starts at login and launches. |
| **macOS / Linux** | `./scripts/install.sh` (same steps; adds a `limitline` command). |
| **Python already** | `pipx install git+https://github.com/<you>/limitline` (or `pip install`), then run `limitline`. |
| **Just trying it** | `python limitline.py --demo` |

First launch shows a three-step welcome window (history found, **Connect** live limits, start with your computer). Nothing needs editing by hand. Check everything with `limitline --selftest`. Remove it with `install.bat -Uninstall` or `./scripts/install.sh --uninstall`; that also restores your previous status line.

Details: [docs/INSTALL.md](docs/INSTALL.md).

## Alerts and the mascot
Alerts can fire at your own levels for the 5-hour and weekly limits, at every N% (say 25 → 50 → 75 → 100), or as a pace warning when you're on course to run out early. Quiet hours and a right-click **Snooze** keep them silent (the banner still shows). A small original character, Tick, pops up beside the widget and changes mood as usage climbs; choose Off, Subtle or Every alert in Settings.

## Controls

| Key / action | What it does |
|---|---|
| Drag the title bar | Move the window |
| Double-click title, `M`, `Esc` | Collapse to / expand from the pill |
| `1` `2` `3` `4` | Switch tabs |
| `R` | Refresh now |
| `T` | Toggle always-on-top |
| `S` | Settings |
| `Ctrl+Q` | Quit |
| Right-click | Menu (export CSV, open logs folder, ...) |

## Command line

| Option | Meaning |
|---|---|
| `--demo [live\|local]` | Sample data |
| `--mini` | Start as the pill |
| `--theme dark\|light` | Theme for this run |
| `--refresh SEC` | Rescan interval |
| `--path DIR` | Extra log folder (repeatable) |
| `--no-live` | Don't fetch live plan limits |
| `--config-dir DIR` | Use another Claude config folder / account (implies `--multi`) |
| `--multi` | Allow more than one copy |
| `--reset` | Forget saved settings |

## Important: what the numbers mean

- **Percentages and reset times** are the ones Claude Code itself reports (status line), so they match what Claude Code shows. They update while Claude Code is open and are refreshed after your next message; the card shows how old they are. Per-model weekly limits (Sonnet / Opus) are not in that feed.
- **Dollar figures and token totals** are *API-equivalent estimates* computed from Claude Code's local session logs, not a bill. On a subscription they show relative effort, not money.
- **How close are they?** In the one real session we could check, the log-derived cost was within about 1% of Claude Code's own cost record at the moment it wrote it (Opus cost matched to the cent); the gap was small background calls. The app compares itself with that record and tells you when the match drops below 97%. Claude Code's record is a snapshot, so the check only compares like with like. This is one session, so treat it as encouraging, not proven.
- Models newer than the built-in price table are priced by assumption and flagged in the footer; set `price_overrides` to fix them.
- Only **Claude Code on this computer** is visible. Claude.ai chat and other machines are not.

More in [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md) and [docs/PRIVACY.md](docs/PRIVACY.md).

## Terms and risk

Anthropic's [legal page](https://code.claude.com/docs/en/legal-and-compliance) says Claude login (OAuth) tokens are for Claude Code and Anthropic's own apps, that third-party developers may not route requests through Free/Pro/Max credentials, and that developers may not "collect, store, or intermediate" those credentials. It also reserves the right to enforce without notice, and there are public reports of accounts affected after using subscription tokens in other tools.

So this project's default path **never touches your login**: live limits come from the status-line data Claude Code hands to a command you configure, which is documented. The optional "Use saved login instead" mode (off by default) reads the token and calls an undocumented Anthropic endpoint; it exists for people who want per-model limits and accept that risk. We are not lawyers and this is not legal advice; if in doubt, leave it off.

## Configuration

Settings are edited in the app (press `S`) and stored in `~/.limitline.json`. Every key is documented in [docs/CONFIGURATION.md](docs/CONFIGURATION.md), including price overrides and alert hooks.

## Project direction

See the [roadmap](docs/ROADMAP.md) (Claude first; Codex and other tools later, behind a quality gate) and the [premortem](docs/PREMORTEM.md) (what could make this fail and what we're doing about it). Feedback from people who keep hitting their limits is the most useful contribution.

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Check it on your computer

```bash
python limitline.py --selftest
```

Runs about 15 checks (window rendering, DPI, fonts, status-line install and undo with quoting, startup entry, notification, logs, a small-laptop fit test) and saves `limitline-selftest.txt` in your home folder. See [docs/WINDOWS_TEST.md](docs/WINDOWS_TEST.md).

## Development

```bash
python tests/test_core.py     # parsing, pricing, windows, aggregation (no display needed)
python limitline.py --demo
```

Contributions welcome. The app is deliberately a single stdlib-only file.

## License

[MIT](LICENSE). Not affiliated with or endorsed by Anthropic. Ideas such as pace markers and alert hooks were inspired by [usage-monitor-for-claude](https://github.com/jens-duttke/usage-monitor-for-claude).
