# Premortem and critique

*Imagine it is a year from now and Limitline failed. Why?*
Written for v2.1, October 2026. Audience: Claude Pro/Max users (mostly Claude Code) who hit the 5-hour or weekly limit without warning.

This document was **tested against the code**, not just brainstormed. Section 1 lists what the audit found and what changed. Sections 2 and 3 are the open risks and an honest critique.

## 1. Audit results (what was found and fixed)

| # | Finding | Severity | Status |
|---|---|---|---|
| A1 | **Terms risk was understated.** Anthropic's [legal page](https://code.claude.com/docs/en/legal-and-compliance) says OAuth tokens are for Claude Code and Anthropic's own apps, third parties may not route requests through Free/Pro/Max credentials, nor "collect, store, or intermediate" them, and enforcement can happen without notice. One secondary source reports an account ban for a Mac app that tracked Claude Code usage (single report, unverified). The v2.0 design read the saved token by default. | Critical | **Fixed.** Default live data now comes from Claude Code's documented [status line](https://code.claude.com/docs/en/statusline) (`rate_limits`), which never touches the login. The token path is opt-in, off by default, with a warning in Settings and the README. |
| A2 | **The "logs undercount" claim was wrong as shipped.** The coverage figure compared the whole, still-growing log with Claude Code's `cost-state` snapshot (one real session showed 183%). Checked properly (log up to the snapshot's position): $9.83 vs $9.91 (99%), Opus cost identical to the cent; the gap was small Haiku background calls. | High (misleading numbers) | **Fixed.** The comparison is now like-for-like, only shown when it drops below 97%, and the README no longer asserts undercounting. Regression test added. |
| A3 | **Bearer token could be forwarded on a redirect** (Python's urllib keeps the Authorization header). | High (security) | **Fixed.** Redirects are never followed; test proves the token is not sent to the redirect target. |
| A4 | Models newer than the price table were silently priced as "newest known". | Medium | **Fixed.** Flagged in the footer; `price_overrides` documented; tests added. |
| A5 | Performance on large histories. | Low | **Checked.** 150,000 messages / 278 MB: first scan 2.7 s, rescan with no change ~0 ms, snapshot 0.75 s, peak memory ~100 MB. |
| A6 | Privacy statement "does not store message text". | Low | **Checked.** Parser keeps counts, model, timestamps, session id and the project folder name only. The live file keeps only `rate_limits`. |
| A7 | Status-line command cost. It runs every time Claude Code refreshes its status line; measured ~120 ms per call (Python start plus compiling the script). | Medium | **Open.** Acceptable but not free; plan: a tiny separate helper script (~25 ms). |

## 2. Open risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Install friction: not everyone has Python/tkinter; unsigned binaries trigger SmartScreen/Gatekeeper | High | High | Prebuilt downloads from CI, winget/Homebrew/Scoop, honest docs on warnings |
| Untested on Windows/macOS (DPI, fonts, frameless window, Keychain-free now, autostart, toasts) | High | High | Beta testers per OS with a checklist; CI screenshot runs on Windows/macOS runners |
| The status-line feed changes or is removed | Low-Med | High | It is documented and versioned; keep the parser tolerant; fall back to local estimates |
| The status-line approach edits the user's Claude Code `settings.json` | Medium | Medium | Backup + exact restore (tested), chains an existing status line, refuses unreadable files. Cannot help if settings are managed by an organisation |
| Feed is thinner than the old method: no per-model weekly limits, no plan name, no extra-usage credit, updates only while Claude Code is open | High | Medium | Say so in the UI; opt-in login mode for those who accept the risk |
| A pricing change or new model makes dollars wrong | Medium | Medium | Footer flag, `price_overrides`, "last checked" date in the price table |
| Claude Code log format changes | Medium | High | Tolerant parser, fixtures per version, "unrecognised format" message instead of zeros |
| Anthropic ships a native widget | Medium | Medium | Good for users; stay complementary (pace, history, alerts, multi-account) |
| Single maintainer, one 3,400-line file | High | Medium | Split into a package with a generated single-file build; CONTRIBUTING; co-maintainer is a launch gate |
| Scope creep into other LLMs | Medium | Medium | Gates in [ROADMAP.md](ROADMAP.md) |

## 3. Critique (what is weak about this project today)

1. **Its main promise is a guess about what users want.** We assume people want a floating window; many may be happier with a status-line line inside Claude Code. The status-line text this app already prints (`5h 24% · 7d 41%`) might satisfy half of them with zero UI. Test that before polishing further.
2. **Dollar figures are API-equivalent, not what subscribers pay.** Showing `$202.62` for a $100/month plan invites confusion. Percent of limit is the number that matters; dollars should be secondary or hidden by default.
3. **The reliable data is smaller than the pitch.** After removing the token path, the guaranteed live data is two percentages and two reset times, only while Claude Code runs. Everything else (pace, history, projects) is estimated from logs.
4. **The evidence base is thin.** The pricing and the "within 1%" result rest on one real session on one machine. New-model prices (e.g. Opus 5.5 at $4/$20 per million) matched Claude Code's own total in that session, but that is one data point.
5. **No automated UI tests.** Core logic is tested (parsing, pricing, windows, bridge, installer, redirect safety); the interface is verified by screenshots on Linux only. CI has never run on Windows/macOS.
6. **Differentiation is modest.** ccusage, usage-monitor-for-claude and CodexBar exist. Our edge: zero-install floating window, pace awareness, no-token default. That has to be said clearly or the project is "yet another tracker".
7. **Naming (fixed in 2.2).** Anthropic's legal page forbids using Claude Code or Anthropic names as part of a product name, and its trademark guidelines allow its marks only as permitted and bar anything implying affiliation. The project was renamed from "Claude Usage" to **Limitline**, with an "unofficial" notice and plain-text references only. Still to do: confirm "Limitline" is free as a GitHub repo and package name, and consider a trademark search before a wide release.
8. **The ban report is unverified**, and the terms are ambiguous about read-only calls. We chose caution; that cost features. If Anthropic confirms read-only monitors are fine, the opt-in mode could move up. Ask them in writing.
9. **Hooks run shell commands from a config file.** Off by default, but a poisoned config file would run code. Document it in SECURITY.md.
10. **Claude.ai chat-only users get nothing** unless they also use Claude Code (the limits are shared but the feed comes from Claude Code).

## 4. Success at 12 months
- Installs in under two minutes on all three OSes without a terminal.
- Live percentage identical to Claude Code's status line; no complaints about numbers in the first month.
- Fewer than 1 in 20 issues are "it doesn't start".
- Two regular contributors besides the maintainer; written answer from Anthropic on the token question.
