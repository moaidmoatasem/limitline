# Limitline UX Testing Plan
Version: 2.0 | Date: 2026-10-09 | Test Engineer: AI Assistant
App Version: v2.12.0 (working tree; HEAD is still b41d096 / v2.3.5) | Platform: Windows 10/11, Python 3.11, tkinter

---

## Executive Summary

App Purpose: Floating desktop monitor for Claude Code usage and plan limits -- gives developers real-time visibility into their 5-hour session window, weekly quotas, spend, and where the work is happening, without leaving their workflow.

Target User: Daily Claude Code users (Pro/Max/Team/Enterprise) who need to monitor rate limits and cost without interrupting their coding flow.

Testing Philosophy: Test like a daily user -- not a QA script. Focus on trust, flow preservation, and actionable information at a glance. The app's core promise is honesty: every number must be traceable to either the local logs or Anthropic's account feed, never a blend pretending to be one thing.

---

## 0. Automated Gates (run before any manual pass)

```
python tests/test_core.py        -> FAILURES: none
python tests/test_render.py      -> FAILURES: none   (needs a display)
python limitline.py --selftest   -> ALL CHECKS PASSED
python limitline.py --demo       -> visual baseline with synthetic data
```

If a gate fails, stop: the manual findings below will be noise on top of a broken build.

---

## 1. Core User Journeys (Daily Workflows)

### Journey 1: Quick Glance -- The 3-Second Check
Trigger: "How much of my 5-hour window is left?" while coding.
Flow:
1. Eyes glance at the widget (or the tray ring/dot hover) in peripheral vision.
2. Ring gauge shows percentage + elapsed marker; the Headroom row answers "can I start a big run?" (<70% heavy models fine, <90% moderate, 90%+ tight, at limit none - advice only, never a ban).
3. Outlook chip and title bar agree with the ring; mini pill shows the same story smaller.
4. Decision made: continue / pace / wrap up.
Success Criteria: < 3 seconds to an actionable answer, zero context switch, and the ring, chip, headroom row, title bar and tray never disagree.

### Journey 2: Deep Dive -- History & Trends
Trigger: End of day/week review: "What did I spend this week?"
Flow:
1. History tab: range segmented control (7d/30d/90d/180d).
2. Per day: value labels on short ranges (<=30d), peak marker on the busiest bucket (exactly one label, marker dot must not sit under text), 7-day rolling-average dashed line whose key lives in the toolbar row (never the card header), weekly bars at 90d+.
3. Cumulative: running-total staircase, flat steps for empty days, two-line hover tooltip (day + running total), explainer on its own full-width line.
4. Heatmap (weekday x hour) and recent 5-hour windows below.
5. Empty range because activity is older? Widen hint with one-click "Show 180d" etc.
6. Export CSV.
Success Criteria: All history visible and correctly grouped; every toolbar/header row fits the card width with no clipped or overlapping text; the source line says "Local Claude Code logs - last activity ...".

### Journey 3: Project Attribution -- Where Did Costs Go?
Trigger: "Which project burned my budget?"
Flow:
1. Projects tab (default 30d; 7d/30d/90d/180d options, widen hint when empty).
2. Per-project rows with percentages, spend and the branch in use ("main", "+2" when spanning branches).
3. Branch names blank when the logs carry none - never invented.
Success Criteria: Worktree sessions roll up to the parent repo, subfolders roll up, branch text matches sessions for the same project.

### Journey 4: Alert Response -- Limit Approaching
Trigger: Threshold banner at 75% / 90% (or per-model weekly thresholds).
Flow:
1. Banner appears at the top of the window (non-modal, non-blocking) plus one desktop notification; the mascot card shows on alert.
2. Dismiss the banner with its "x"; during snooze or quiet hours the banner still shows - it is the only visible trace while hooks and sound stay silent.
3. Snooze from the tray/context menu ("Snooze alerts" 15m/1h/..., "Resume alerts").
4. Weekly caps at >= 90%: persistent "Weekly cap critical" card naming the limit + reset time, with "Review thresholds" (opens Settings) and "Snooze 1h". Below 90%, or with no feed, it renders nothing.
5. Settings: per-model thresholds (`alert_levels_week_*`), pace bypass, hook commands with working "Test" buttons.
Success Criteria: Alerts noticed but never break flow; scope toggle on Overview does not change alert behaviour (alerts always run on full data); 5-hour windows never trigger the weekly emergency card.

### Journey 5: Setup & Connect -- First Run
Trigger: First launch / new machine.
Flow:
1. Welcome window: detects logs, one-click Connect (status line installed, zero config).
2. Saved-login path is opt-in in Settings; when enabled shows account email + prepaid balance (memory only, never written to settings); auto-refresh is off by default.
3. First Claude Code message -> live data appears.
4. Mini pill mode (double-click the title or press M; Esc collapses to the pill); keyboard shortcuts: R refresh, T always-on-top, S settings, 1-4 tabs, Ctrl+Q quit.
5. Tray (opt-in, `pip install "limitline[tray]"`): degrades gracefully when packages are missing; Settings row says so.
Success Criteria: Zero-config for the status line; every opt-in (saved login, auto-refresh, tray) is clearly optional; icon smooth in taskbar, tray and ALT+TAB.

### Journey 6: Data-Scope Check (Overview toggle)
Trigger: User toggles Claude Code / Claude (all) / Both.
Flow:
1. "Claude Code": ring, chip, pace rows and projections all derive from local logs against the local limit. No "of plan" caption, no "Limit by ..." ETA, no account percentages anywhere on the card.
2. "Claude (all)": account-wide ring + plan limits only. Without a live feed: honest "no plan data" empty ring and chip - never a local estimate. History/Projects/Sessions show a placeholder explaining account data carries no per-day detail, with one-click "Show Claude Code" / "Show Both".
3. "Both": labelled view (ring from live feed, local figures marked as such).
4. Choice persists across restart; alerts and CSV export are unaffected by scope.
Success Criteria: No figure ever mixes the two sources; switching scopes never loses data or throws; placeholder never appears in local/both.

### Journey 7: Live Sessions Drill-Down
Trigger: "Which run is expensive right now?"
Flow:
1. Sessions tab: KPI strip (live runs, 7-day spend + avg/run, 30-day tokens + cache-hit rate, top group + share).
2. Groups by project + branch, richest first, runs newest first; expandable blocks with a spend-concentration badge (wording is cautious: a share/dollar fact, never a claimed root cause).
3. Live filter: project/branch/session search, Running/Done pills (activity-based, not process handles), model-family chips.
4. Click a run -> read-only inspector: token legs largest first with exact total beside them, cache-hit rate with counts, Claude Code's billed total vs the logs' figure with a match %, Copy session ID, Export group (counts/costs only).
5. Overview's "Live right now" / "Recent runs" cards cross-link here with the filter reset to all.
Success Criteria: Grouping and totals add up; no process controls exist anywhere (no attach/pause/kill); export and tips contain no token or message text.

### Journey 8: "Can I Start a Big Run?" (Overview)
Trigger: Before kicking off a long agent run.
Flow:
1. Headroom row gives tiered advice from the shown percentage, and agrees with the active scope (local scope grades the local limit; account scope grades the plan; no feed says so).
2. 24-hour chart's pace sentence: peak tok/h with its hour, avg tokens per message, cache-hit rate - honest Nones when there is nothing to average, never dressed-up zeros.
3. Weekly emergency card only if a weekly cap is >= 90%.
4. Live right now / recent runs cards show what is already in flight.
Success Criteria: The recommendation can be followed literally (a "heavy models fine" reading below 70%); every figure in the sentence is reproducible from the data shown elsewhere.

---

## 2. UI/UX Validation Checklist

### 2.1 Visual Hierarchy & Information Architecture
- [ ] Four tabs in order (Overview, History, Projects, Sessions); 1-4 keys switch them.
- [ ] Most urgent item (ring / emergency / alert) is the largest thing on the screen.
- [ ] Identity is never colour-only: severity chips carry shape + word, legend swatches carry labels.
- [ ] Light and dark themes both readable; accent setting follows through icon, ring, charts.
- [ ] KPI strips scan left-to-right; elided long names stay identifiable.

### 2.2 Data Honesty & Scope
- [ ] Local-only numbers say so ("Local Claude Code logs ..."); account numbers say "of plan" / "Anthropic's numbers for your whole account".
- [ ] Empty states are actionable (widen hint, connect button, "no plan data"), never a dead end or a fake zero.
- [ ] Unknown quota types show a NEW badge instead of vanishing; unrecognized quota never renders as a phantom 0%.
- [ ] Concentration badges state a share or dollar amount, never a cause; no "throttled" wording exists.
- [ ] Bill-vs-logs match % only appears when the billed figure is fresh.

### 2.3 Charts & Text Fit (Regression Hotspots)
Known traps that have broken before -- check every one at 100%/150%/200% scale and at the minimum window width:
- [ ] Peak marker dot must not overlap the value label it replaces (busiest bucket labelled exactly once).
- [ ] 7-day avg key sits in the toolbar row; card header holds title + family legend only.
- [ ] Four model families fit the header; five families is a known pre-existing squeeze (day/weekly header can clip) - confirm no worse than before, log if visible.
- [ ] Cumulative explainer on its own line; mode toggle + key row must fit the content width (a previous build overflowed by 134px).
- [ ] Trend line starts at the first full 7-day window, not a partial one.
- [ ] Axis/value labels inside the canvas bounds; no text cut at card edges; heat map squares aligned.
- [ ] Headroom row, velocity sentence and run-card rows wrap or elide instead of pushing the card wider.

### 2.4 Settings & Configuration
- [ ] Settings fits 1366x768 (scrolls rather than clipping) and a large screen without gaps.
- [ ] Editing `.limitline.json` while running reloads live; invalid values fall back to defaults (scope -> both, hist_mode -> day, etc).
- [ ] Hook rows: shell and argv-list commands both work; "Test" button reports exit code + output.
- [ ] Config-file-only keys are not in the UI and are not stripped by save.
- [ ] Tray row explains missing optional packages instead of failing.

### 2.5 Alerts & Feedback
- [ ] Banner is non-modal; "x" dismisses it; tray/context menu snooze (15m/1h/...) and "Resume alerts" work.
- [ ] Banner + desktop notification arrive together; during snooze or quiet hours the banner still shows while sound, notification and hooks stay silent.
- [ ] Emergency card: appears only at >=90% weekly, names limit + reset, "Review thresholds" opens Settings, "Snooze 1h" silences it, card vanishes below threshold or without a feed.
- [ ] Mascot card appears once per alert event, never loops; sound respects snooze.
- [ ] Changing thresholds takes effect without restart.

### 2.6 Chrome & Platform
- [ ] App icon smooth at 16/32/48/256 (taskbar, tray, ALT+TAB, window corner).
- [ ] Always-on-top (T) survives tab switches; frameless/mini pill restore cleanly (double-click title).
- [ ] Windows rounded-corner/dark title-bar call completes; window remembers size/position.
- [ ] First-run welcome and selftest report render both themes without exception.

### 2.7 Trust & Privacy
- [ ] No message text and no API tokens anywhere in UI, tips, exports, logs or alert hooks; usage numbers (token counts, costs, cache hits) are of course fine. Export group = counts and costs only; session ID is an ID.
- [ ] Saved-login credentials never appear in `.limitline.json` or Settings screenshots; email/prepaid live in memory only.
- [ ] Runtime files are exactly: `.limitline.json`, `.limitline-live.json`, `.limitline-logcheck.json`, `.limitline-login-check.json`, `.limitline-statusline-note.txt`.

---

## 3. Environment Matrix

Vary at least these axes while running the journeys:
- Feed: status-line bridge / saved-login (opt-in) / no feed (auto estimates) / `--demo`.
- Logs: rich history / empty current range with older activity (widen path) / no logs at all.
- Theme: light, dark. Scale: 100%, 150%, 200%.
- Window: default, minimum width, mini pill, 1366x768 laptop.
- Tray: installed / not installed. Python: 3.11 and, if available, 3.8 (support floor).
- Scope: local / all / both, on every journey that touches Overview.

---

## 4. Pass Criteria

- All automated gates green before and after any fix.
- Every journey's success criteria met in at least the demo + one real-feed configuration.
- No clipped, overlapping or truncated text anywhere in the matrix; no exception dialogs; no mixed-source figures.
- Findings logged with tab, scope, theme, scale, feed state and a screenshot; severity = trust bug > fit bug > polish.
