# Roadmap

**Focus: make the Claude MVP excellent first.** Other LLM tools are planned for, not built, until the gate at the end of Phase 1 is met.

## Phase 0: harden (now, v2.x)
- [ ] Beta test (use `--selftest` and docs/WINDOWS_TEST.md) on real Windows 10/11, macOS (Intel + Apple Silicon), Ubuntu/Fedora; fix DPI, fonts, frameless and autostart issues
- [ ] Prebuilt downloads from GitHub Actions (Windows .exe, macOS .app, Linux AppImage)
- [ ] Log fixtures from several Claude Code versions in `tests/fixtures`
- [ ] Unknown models flagged in the UI; pricing table with a "last checked" date
- [ ] SECURITY.md, CONTRIBUTING.md, issue templates (bug per OS, "numbers look wrong")
- [x] Live limits via Claude Code's official status line; the saved-login path is opt-in and off by default
- [ ] Ask Anthropic (support / developer relations) in writing whether a read-only usage monitor may use the subscription token, and publish the answer

## Phase 1: public MVP (v3.0)
- [ ] One-line install per OS; winget / Homebrew cask / Scoop entries
- [ ] Tray / menu-bar icon showing the percentage (optional dependency, app still works without it)
- [ ] Claude Code statusline integration (show the same numbers inside Claude Code)
- [ ] Optional small MCP server so Claude itself can answer "how much of my limit is left?" (read-only)
- [ ] Translations (Arabic first, with right-to-left layout)

**Gate to start multi-provider work:** 4 weeks with no open crash bugs, live numbers equal to Claude Code's own status line, installs reported working on all three OSes, at least one co-maintainer.

## Phase 2: refactor for providers (v3.x)
Split the single file into a package; keep a generated single-file build for people who want it.

```
usage_monitor/
  core/        model.py (events, limits), aggregate.py, pricing.py
  providers/   base.py, claude_code.py   <- the only provider at first
  ui/          tk app, widgets, gfx rasteriser
  cli.py
```

Provider interface (draft):

```python
class Provider:
    id: str                      # "claude-code", "codex", ...
    label: str
    def detect(self) -> bool                     # is this tool installed / used here?
    def scan(self, since) -> list[UsageEvent]    # incremental, from local logs
    def limits(self) -> LimitSnapshot | None     # live plan limits, if any
    def price(self, model, usage) -> float | None

UsageEvent: ts, provider, model, input, output, cache_write, cache_read, reasoning, cost, project, session
LimitSnapshot: provider, windows=[{key, label, pct, resets_at}], plan, source ("live"|"estimate"), fetched_at
```

The UI then shows one card per provider plus a combined "today" view. Pace, alerts and hooks work per limit window, whatever the provider.

## Phase 3: other tools (research first, one at a time)

Each provider starts as a research spike with a short write-up: where the data lives, how stable it is, whether it has live limits, and any terms concerns. Only then is it built.

| Tool | Local usage data | Live limits | First impression |
|---|---|---|---|
| OpenAI Codex CLI | `~/.codex/sessions/YYYY/MM/DD/*.jsonl` (`token_count` events) | ChatGPT backend endpoint with the Codex login, or `codex` app-server JSON-RPC | Best next candidate; similar 5-hour + weekly model |
| OpenCode | `~/.local/share/opencode/` | n/a (bring-your-own key) | Easy, tokens only |
| Amp CLI | `~/.local/share/amp/threads/` | unknown | Research |
| Gemini CLI | to research | to research | Research |
| Cursor / Windsurf / Copilot | mostly server-side | dashboards only | Probably out of scope |
| ChatGPT / Claude web chat | no local data | only via browser cookies | Out of scope: fragile and risky |
| API keys (Anthropic, OpenAI) | n/a | official usage/cost Admin APIs | Possible "API spend" provider, needs an admin key |

Rules for adding a provider:
1. Read-only. Never write to another tool's files or refresh its tokens.
2. Official or documented sources first; undocumented endpoints are opt-in and clearly labelled.
3. Each provider is optional and isolated: a failure in one never blocks the others.
4. Fixture tests ship with the provider.

## Not planned
- Cloud sync or accounts. Everything stays on the user's computer.
- Collecting usage data from users.
