# Limitline Test Plan (Updated for v2.3.4 + B5/B6)

**Last updated**: 2026-10-09
**Scope**: v2.3.4 released + B5 (idle-aware polling) + B6 (NEW badge for unknown quotas)
**Goal**: Ship-ready confidence for v2.3.5

---

## 1. Coverage Matrix (Current vs. Target)

| Area | Current Coverage | Target | Status |
|------|-----------------|--------|--------|
| Log parsing | Excellent (dedupe, incremental, malformed) |  | Done |
| Project naming | Good (worktree, subfolder, plain, UNC) |  | Done |
| Pricing/cost | Good (known models, old names, costUSD) |  | Add: unknown model fallback, fast-mode, batch API |
| Live limits (statusline) | Good (parse_live, extra_usage, per-model, ISO resets) |  | Add: rate-limit backoff, concurrent fetch, auth refresh |
| Live limits (OAuth) | Basic (fetch, parse, no-redirect) |  | Add: token refresh, 401 handling, scope validation |
| Spend alerts (A1) | Good (threshold, monthly re-arm, defaults off) |  | Add: spend+forecast interaction, spend+quiet hours, partial month |
| Forecast/pace alerts | Good (threshold, forecast, pace-only, quiet, snooze, hooks) |  | Done |
| Start command (A4) | Basic |  | Add: command failure, demo mode, rapid restarts |
| Install detection (A3) | Good (PATH, VS Code, Cursor, failures) |  | Add: JetBrains plugins, multiple versions, WSL fallback |
| Adaptive poll (B5) | Good (pure fn, idle, resets, statusline) |  | Add: config changes mid-run, probe failures, clock skew |
| New quota badge (B6) | Basic (ordering, Fable/Cowork) |  | Add: tooltip on badge, multiple unknown, locale |
| Render widgets | Basic (BarChart, Heatmap, meter) |  | Major gap: Overview ring, Composition, Session list, Projects list |
| Status line bridge | Good (basic, UTF-8, chaining, per-model, ISO) |  | Add: large payloads, rate limit, binary corruption |
| Config/DB | Good (corrupt backup, locked retry, version match) |  | Add: migration from old formats, cross-account isolation |
| Hooks | Good (alert, reset, startup, quiet, snooze) |  | Add: hook timeout, stdout/stderr capture, env var expansion |
| Mascot | Basic (mood, caption, shapes) |  | Add: animation frames, reduced motion, click dismiss |

---

## 2. Real-Data Test Enhancement (Priority: High)

Current state: Lines 193-228 in test_core.py compare per-session costs against Claude Code's own cost-state records using the local ~/.claude/projects logs. This is excellent but needs:

### 2.1 Extract to Dedicated Test File
Create tests/test_realdata.py:
- Opt-in via env var LIMITLINE_TEST_REALDATA=1
- Runs only when ~/.claude/projects exists and has cost-state records
- Skips cleanly otherwise (CI-friendly)
- Outputs comparison table for manual review

### 2.2 Additional Real-Data Checks to Add
```python
# 1. Cost coverage per session (logged vs billed)
#    Target: >=97% match (current check: <=3% worst case)

# 2. Token accounting per session
#    - outputTokens match
#    - cacheReadInputTokens match
#    - cacheCreationInputTokens match (when available)

# 3. Model usage breakdown matches modelUsage in cost-state
#    - per-model tokens, costs

# 4. Session duration from first/last message vs Claude Code window
#    - verify 5-hour window boundaries align

# 4. Weekly rollup (7d) matches Claude Code seven_day percentage
#    - requires live OAuth or statusline data

# 5. Project grouping accuracy
#    - worktree sessions -> parent repo
#    - subfolder sessions -> project root
#    - WSL paths -> correct repo name

# 6. Cost-state timestamp alignment
#    - cost-state recorded at time T -> log entries up to T should match
#    - later log entries for same session should NOT affect that cost-state comparison

# 7. Incremental scan correctness
#    - scan, append entries, re-scan -> no duplicates, no misses
#    - truncate file -> re-read from start
```

### 2.3 Test Fixtures for Real Data
tests/fixtures/realdata/
  - sample_cost_state.jsonl      (cost-state records)
  - sample_session_logs.jsonl    (full session with all message types)
  - sample_worktree_logs.jsonl   (WSL paths, worktree cwd)
  - sample_unicode_paths.jsonl   (Unicode in cwd)
  - sample_large_session.jsonl   (1000+ messages)

---

## 3. Recent Changes Integration (B5 + B6)

### 3.1 B5: Idle-Aware Polling - Tests Added
Already in test_core.py lines 127-139:
- live_interval() pure function tests (activity, staleness, resets, idle, bridge)
- os_idle_seconds() probe test

Missing B5 tests to add:
```python
# 1. live_interval with config change mid-run (live_interval_sec updated)
# 2. live_interval with probe failure (os_idle_seconds returns None)
# 3. live_interval with clock skew (now < last_ts)
# 4. LiveLimits.loop: interval respects idle cap but resets win
# 4. LiveLimits.loop: source=statusline keeps 10s cadence even when idle
# 5. LiveLimits.fetch: rate limit backoff (429) doubles interval
# 6. LiveLimits.fetch: 401/403 -> status=auth, no crash
# 7. LiveLimits.fetch: network timeout -> status=offline, retry
# 8. LiveLimits.fetch: invalid JSON -> status=error, no crash
```

### 3.2 B6: NEW Badge for Unknown Quotas - Tests Added
Already in test_core.py lines 118-125:
- Unknown keys appear, ordered last
- Fable/Cowork in LIVE_LABELS -> no badge

Missing B6 tests to add:
```python
# 1. NEW badge tooltip text ("New limit type - check for app update")
# 2. Multiple unknown keys in same response
# 3. Unknown key with seven_day_ prefix vs five_hour_ prefix
# 4. Unknown key with extra_usage-like key
# 5. Footer message appears when any unknown key present
# 6. Badge color/theme consistency (raised background, ink2 text)
```

---

## 4. Test File Structure (Proposed)

tests/
test_core.py           # 536 lines - unit/functional (all passing)
test_render.py         # 107 lines - widget rendering (needs display)
test_realdata.py       # NEW - real log comparison (opt-in)
test_integration.py    # NEW - end-to-end scenarios
test_perf.py           # NEW - benchmarks (pytest-benchmark)
fixtures/
  realdata/
    sample_cost_state.jsonl
    sample_session_logs.jsonl
    sample_worktree_logs.jsonl
    sample_unicode_paths.jsonl
    sample_large_session.jsonl
conftest.py            # pytest fixtures, markers

---

## 5. CI/CD Integration (Proposed)

```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python: [3.8, 3.9, 3.10, 3.11, 3.12]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: ${{ matrix.python }} }
      - name: Install deps
        run: pip install pytest pytest-xvfb hypothesis pytest-benchmark
      - name: Run unit tests
        run: python -m pytest tests/test_core.py -v
      - name: Run render tests
        uses: GabrielBB/xvfb-action@v1
        if: runner.os == Linux
        with:
          run: python -m pytest tests/test_render.py -v
      - name: Run render tests (Windows/macOS)
        if: runner.os != Linux
        run: python -m pytest tests/test_render.py -v
      - name: Real data tests (local only)
        if: env.LIMITLINE_TEST_REALDATA == 1
        run: python -m pytest tests/test_realdata.py -v
      - name: Py38 syntax check
        run: python -c "import ast; ast.parse(open('limitline.py').read(), feature_version=(3,8))"
      - name: Version sync check
        run: python -c "import re; v=re.search(r'version = \"(.+)\"', open('pyproject.toml').read()).group(1); assert v == open('limitline.py').read().split('VERSION = ')[1].split('\n')[0].strip('\"')"
```

---

## 5. Immediate Next Steps (Recommended Order)

| Step | Task | Est. Effort |
|------|------|-------------|
| 1 | Create tests/test_realdata.py with opt-in env var | 1 session |
| 2 | Add missing B5 tests (8 items) to test_core.py | 1 session |
| 3 | Add missing B6 tests (6 items) to test_core.py | 0.5 session |
| 4 | Create tests/test_integration.py skeleton (5 scenarios) | 1 session |
| 4 | Add pytest + xvfb + hypothesis to dev deps | 0.25 session |
| 5 | Run manual visual checklist on Windows | 0.5 session |
| 6 | Run real-data test locally with LIMITLINE_TEST_REALDATA=1 | 0.25 session |
| 6 | Set up GitHub Actions workflow | 0.5 session |

---

## 6. Questions for Clarification

1. Real-data test: Should I create test_realdata.py now with the 8 additional checks, or expand the existing section in test_core.py?
2. B5/B6 tests: Should I add the 14 missing tests now, or batch them with the integration tests?
3. Real data fixtures: Want me to snapshot your current ~/.claude data as regression fixtures?
4. CI/CD: Set up GitHub Actions now, or wait until after local verification?
5. pytest migration: The current check() function works well. Migrate to pytest now for fixtures/parametrize, or keep custom runner?
6. Performance baselines: Add pytest-benchmark now, or just manual notes?

---

## 6. Risk Register (Updated)

| Risk | Likelihood | Impact | Current Mitigation | Gap |
|------|------------|--------|-------------------|-----|
| UI regression on DPI/theme | Medium | High | test_render.py (3 widgets) | 7 widgets untested |
| Status-line breakage on CC update | Medium | High | Bridge tests with multiple payloads | No version matrix |
| Hook command injection | Low | Critical | shell=True documented, env vars only | No input validation |
| Config corruption on crash | Low | High | Atomic writes + .bad backup | No crash test |
| Memory leak on long runs | Low | Medium | Manual stress test | No automated soak test |
| WSL path resolution | Medium | Medium | Worktree fallback works | No WSL CI test |
| Cost-state timestamp drift | Medium | High | Like-for-like comparison (lines 193-228) | No automated regression |
| Model pricing drift | Medium | Medium | price_status() flags unknown | No auto-update from Anthropic |

---

Ready to execute when you approve. Which items should I tackle first?
