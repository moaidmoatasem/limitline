"""Real-data regression tests for Limitline.

Run with: LIMITLINE_TEST_REALDATA=1 python tests/test_realdata.py

This test compares Limitline computed metrics against Claude Code's own
cost-state records from the local ~/.claude/projects logs.
Requires a real Claude Code installation with cost-state records.
Skips cleanly if no data available.
"""
import os, sys, json, glob, time, math
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import limitline as c

if not os.environ.get("LIMITLINE_TEST_REALDATA"):
    print("SKIP: Set LIMITLINE_TEST_REALDATA=1 to run real-data tests")
    sys.exit(0)

print("=" * 60)
print("REAL-DATA REGRESSION TESTS")
print("=" * 60)

real = os.path.expanduser("~/.claude/projects")
if not os.path.isdir(real):
    print(f"SKIP: {real} does not exist")
    sys.exit(0)

rs = c.LogStore()
rs.scan([real], 0)
res = rs.entries(0)

# Collect cost-state records from logs
cc_recs = {}
for p in glob.glob(os.path.join(real, "**", "*.jsonl"), recursive=True):
    for ln in open(p, encoding="utf-8", errors="replace"):
        if '"cost-state"' not in ln:
            continue
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        if d.get("type") == "cost-state" and d.get("sessionId"):
            cc_recs[str(d["sessionId"])] = d

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

# 1. Per-session cost coverage
if rs.cost_states:
    worst = 0.0
    for sid, (bill, logged_then) in sorted(rs.cost_states.items()):
        rel = abs(bill - logged_then) / max(bill, 1e-9)
        worst = max(worst, rel)
        pct = (1 - rel) * 100
        print(f"  session {sid[:8]}: mine ${logged_then:.4f} vs CC ${bill:.4f} ({pct:.1f}% match)")

        d = None
        for rec in rs.cost_states.get(sid, []):
            pass
        cc_rec = None
        for p in glob.glob(os.path.join(real, "**", "*.jsonl"), recursive=True):
            for ln in open(p, encoding="utf-8", errors="replace"):
                if '"cost-state"' not in ln:
                    continue
                try:
                    d = json.loads(ln)
                except ValueError:
                    continue
                if d.get("type") == "cost-state" and str(d.get("sessionId")) == sid:
                    cc_rec = d
                    break
            if cc_rec:
                break

        d = cc_rec or {}
        mu = d.get("modelUsage") or {}
        if mu:
            cc_out = sum(int(m.get("outputTokens") or 0) for m in mu.values())
            cc_cr = sum(int(m.get("cacheReadInputTokens") or 0) for m in mu.values())
            full = sum(e.cost for e in res if e.session == sid)
            if abs(full - logged_then) < 1e-9:
                mine = [e for e in res if e.session == sid]
                check(sum(e.out for e in mine) == cc_out,
                      f"session {sid[:8]}: outputTokens match ({sum(e.out for e in mine)} vs {cc_out})")
                check(sum(e.cr for e in mine) == cc_cr,
                      f"session {sid[:8]}: cacheReadInputTokens match ({sum(e.cr for e in mine)} vs {cc_cr})")

                # cache creation if available
                cc_cw = sum(int(m.get("cacheCreationInputTokens") or 0) for m in mu.values())
                check(sum(e.cw for e in mine) == cc_cw,
                      f"session {sid[:8]}: cacheCreationInputTokens match ({sum(e.cw for e in mine)} vs {cc_cw})")

                # per-model breakdown
                for m in mu.values():
                    model = m.get("model", "unknown")
                    expected_out = int(m.get("outputTokens") or 0)
                    expected_cr = int(m.get("cacheReadInputTokens") or 0)
                    expected_cw = int(m.get("cacheCreationInputTokens") or 0)
                    mine_model = [e for e in mine if e.model == model]
                    if mine_model:
                        check(sum(e.out for e in mine_model) == expected_out,
                              f"session {sid[:8]} model {model}: outputTokens match")
                        check(sum(e.cr for e in mine_model) == expected_cr,
                              f"session {sid[:8]} model {model}: cacheRead match")
                        check(sum(e.cw for e in mine_model) == expected_cw,
                              f"session {sid[:8]} model {model}: cacheWrite match")

    check(worst <= 0.03, f"per-session cost matches CC record (worst {worst * 100:.1f}%)")
else:
    print("  no cost-state records - comparison skipped")

print()
print("=" * 60)
print("FAILURES:", fails if fails else "none")
print("=" * 60)

if fails:
    sys.exit(1)
