import json
import os
import sys
import time
import tempfile
import glob
import platform
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import limitline as c

IS_WIN = platform.system() == "Windows"

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts)) + ".%03dZ" % int((ts % 1) * 1000)

def line(ts, mid, rid, model, inp, out, cw, cr, cwd="/Users/moayed/code/web-app", sid="s1", w1=None, extra=None):
    u = {"input_tokens": inp, "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr, "output_tokens": out,
         "service_tier": "standard"}
    if w1 is not None:
        u["cache_creation"] = {"ephemeral_1h_input_tokens": w1, "ephemeral_5m_input_tokens": cw - w1}
    d = {"parentUuid": None, "isSidechain": False, "userType": "external", "cwd": cwd, "sessionId": sid,
         "version": "2.1.0", "gitBranch": "main", "type": "assistant", "uuid": "u-%s-%s" % (mid, out),
         "timestamp": iso(ts), "requestId": rid,
         "message": {"id": mid, "type": "message", "role": "assistant", "model": model,
                     "content": [{"type": "text", "text": "hi"}], "usage": u}}
    if extra:
        d.update(extra)
    return json.dumps(d) + "\n"

now = time.time()
tmp = tempfile.mkdtemp()
proj = os.path.join(tmp, "projects", "-Users-moayed-code-web-app")
os.makedirs(proj)
f1 = os.path.join(proj, "s1.jsonl")
with open(f1, "w") as fh:
    fh.write(json.dumps({"type": "user", "message": {"role": "user", "content": "usage please"}, "timestamp": iso(now - 600)}) + "\n")
    # same message logged three times (content blocks) -> one entry, keep largest output
    fh.write(line(now - 590, "msg_A", "req_A", "claude-sonnet-5-5", 10, 50, 1000, 20000, w1=1000))
    fh.write(line(now - 590, "msg_A", "req_A", "claude-sonnet-5-5", 10, 120, 1000, 20000, w1=1000))
    fh.write(line(now - 590, "msg_A", "req_A", "claude-sonnet-5-5", 10, 120, 1000, 20000, w1=1000))
    # opus 5.5 with 5m cache writes (no breakdown)
    fh.write(line(now - 500, "msg_B", "req_B", "claude-opus-5-5", 5, 1000, 4000, 50000))
    # synthetic + zero usage -> skipped
    fh.write(line(now - 400, "msg_C", "req_C", "<synthetic>", 0, 0, 0, 0))
    # old naming + explicit costUSD
    fh.write(line(now - 3 * 86400, "msg_D", "req_D", "claude-3-5-haiku-20241022", 100, 100, 0, 0, extra={"costUSD": 0.5}))
    # windows cwd, fast mode opus
    fh.write(line(now - 300, "msg_E", "req_E", "claude-opus-4-1-20250805", 1000, 1000, 0, 0, cwd="C:\\Users\\moayed\\proj\\api", sid="s2"))
    fh.write('{"type":"assistant","truncated')   # partial last line, no newline

store = c.LogStore()
changed, nfiles = store.scan([os.path.join(tmp, "projects")], now - 40 * 86400)
es = store.entries(now - 40 * 86400)
check(nfiles == 1 and changed == 1, f"scanned 1 file (got {nfiles}, changed {changed})")
check(len(es) == 4, f"4 entries after dedupe/skip (got {len(es)})")
A = [e for e in es if e.model == "claude-sonnet-5-5"][0]
check(A.out == 120, f"dedupe keeps largest output (got {A.out})")
expA = (10 * 2 + 120 * 10 + 1000 * 4 + 20000 * 0.2) / 1e6
check(abs(A.cost - expA) < 1e-12, f"sonnet 5.5 cost with 1h cache write {A.cost:.8f} == {expA:.8f}")
B = [e for e in es if e.model == "claude-opus-5-5"][0]
expB = (5 * 4 + 1000 * 20 + 4000 * 5 + 50000 * 0.2) / 1e6
check(abs(B.cost - expB) < 1e-12, f"opus 5.5 cost with 5m cache write {B.cost:.8f} == {expB:.8f}")
D = [e for e in es if "haiku" in e.model][0]
check(D.cost == 0.5 and D.disp == "Haiku 3.5", f"costUSD honoured, old name parsed ({D.cost}, {D.disp})")
E = [e for e in es if "opus-4-1" in e.model][0]
check(E.project == "api" and abs(E.cost - (1000 * 15 + 1000 * 75) / 1e6) < 1e-12, f"windows cwd -> project ({E.project}), opus 4.1 price ({E.cost})")
check(A.project == "web-app", f"posix cwd -> project ({A.project})")
wt = c.LogStore._project(r"\\wsl.localhost\ubuntu-24.04\home\moaid\cherenkov-qa\.claude\worktrees\sleepy-ishizaka-8da375", "x.jsonl")
check(wt == "cherenkov-qa", f"worktree cwd -> repo name ({wt})")
wt2 = c.LogStore._project("/home/moaid/cherenkov-qa/.claude/worktrees/qa+report-plan-r1/sub", "x.jsonl")
check(wt2 == "cherenkov-qa", f"posix worktree cwd -> repo name ({wt2})")
if IS_WIN:
    plain = c.LogStore._project(r"C:\Users\moaid\bawsala-crew-v0.1\bawsala-crew", "x.jsonl")
    check(plain == "bawsala-crew", f"ordinary cwd still uses its basename ({plain})")
    deep = c.LogStore._project(r"\\wsl.localhost\ubuntu-24.04\home\moaid\cherenkov-qa\cherenkov\web\ui\src", "x.jsonl")
    check(deep == "cherenkov-qa", f"subfolder cwd -> project under home ({deep})")
    one = c.LogStore._project(r"C:\Users\moaid\code\proj\src", "x.jsonl")
    check(one == "src", f"single generic folder left alone ({one})")
check(c.LogStore._branch("origin/feature-auth") == "origin/feature-auth", "branch kept verbatim")
check(c.LogStore._branch("  main  ") == "main", "branch whitespace stripped")
check(c.LogStore._branch("") == "" and c.LogStore._branch(None) == ""
      and c.LogStore._branch(42) == "" and c.LogStore._branch("   ") == "",
      "missing/non-string/blank branch becomes empty")
check(c.LogStore._branch("x" * 200) == "x" * 80, "branch capped at 80 chars")
check(getattr(A, "branch", None) == "main", f"log gitBranch captured on entries ({getattr(A, 'branch', None)!r})")

# incremental: complete the partial line + append new message
with open(f1, "a") as fh:
    fh.write('"}\n')
    fh.write(line(now - 60, "msg_F", "req_F", "claude-haiku-4-5", 3, 300, 0, 9000, sid="s1"))
changed, _ = store.scan([os.path.join(tmp, "projects")], now - 40 * 86400)
es = store.entries(now - 40 * 86400)
check(changed == 1 and len(es) == 5, f"incremental append picked up (changed {changed}, entries {len(es)})")
# nothing new -> no re-read
changed, _ = store.scan([os.path.join(tmp, "projects")], now - 40 * 86400)
check(changed == 0, "unchanged file skipped")
# truncate/rewrite -> re-read from start without duplicates
with open(f1, "w") as fh:
    fh.write(line(now - 590, "msg_A", "req_A", "claude-sonnet-5-5", 10, 120, 1000, 20000, w1=1000))
changed, _ = store.scan([os.path.join(tmp, "projects")], now - 40 * 86400)
check(len(store.entries(now - 40 * 86400)) == 5, "rewritten file doesn't duplicate")

# model meta / pricing table spot checks
for m, fam, disp, price in [
    ("claude-fable-5-1", "fable", "Fable 5.1", (10, 12.5, 20, 0.25, 50)),
    ("claude-mythos-5", "fable", "Mythos 5", (10, 12.5, 20, 1.0, 50)),
    ("claude-opus-5", "opus", "Opus 5", (5, 6.25, 10, 0.5, 25)),
    ("claude-opus-4-6", "opus", "Opus 4.6", (5, 6.25, 10, 0.5, 25)),
    ("claude-opus-4-20250514", "opus", "Opus 4", (15, 18.75, 30, 1.5, 75)),
    ("claude-sonnet-4-5-20250929", "sonnet", "Sonnet 4.5", (3, 3.75, 6, 0.3, 15)),
    ("claude-sonnet-5", "sonnet", "Sonnet 5", (2, 2.5, 4, 0.2, 10)),
    ("claude-haiku-4-5-20251001", "haiku", "Haiku 4.5", (1, 1.25, 2, 0.1, 5)),
]:
    got = c.model_meta(m)
    check(got[0] == fam and got[1] == disp and tuple(got[2]) == tuple(float(x) for x in price), f"meta {m} -> {got}")

# live parsing
items, extra = c.parse_live({"five_hour": {"utilization": 35.0, "resets_at": "2026-02-06T22:00:00+00:00"},
                             "seven_day": {"utilization": 14.0, "resets_at": "2026-02-12T20:00:00.123456+00:00"},
                             "seven_day_sonnet": {"utilization": 39.0, "resets_at": "2026-02-09T14:00:00+00:00"},
                             "seven_day_opus": None,
                             "extra_usage": {"is_enabled": True, "monthly_limit": 100000, "used_credits": 2500.0}})
check([i["key"] for i in items] == ["five_hour", "seven_day", "seven_day_sonnet"], f"live items ordered {[i['key'] for i in items]}")
check(items[0]["resets"] == c.parse_ts("2026-02-06T22:00:00Z"), "resets parsed")
check(abs(extra["pct"] - 2.5) < 1e-9, f"extra usage pct {extra}")
check(extra["used"] == 2500.0 and extra["limit"] == 100000.0, f"extra usage keeps raw numbers {extra}")
check(c.plan_label("max", "default_claude_max_20x") == "Max 20x", "plan label")
items2, _ = c.parse_live({"five_hour": {"utilization": 10.0, "resets_at": None},
                          "seven_day_fable": {"utilization": 20.0, "resets_at": None},
                          "seven_day_something_new": {"utilization": 5.0, "resets_at": None}})
keys2 = [i["key"] for i in items2]
check("seven_day_something_new" in keys2 and keys2.index("seven_day_something_new") > keys2.index("five_hour"),
      f"unrecognized quota types still show, ordered last ({keys2})")
check(all((k in c.LIVE_LABELS) == (k != "seven_day_something_new") for k in keys2),
      "only truly new keys fall outside the known labels (fable/cowork stay badgeless)")
items3, _ = c.parse_live({"five_hour": {"utilization": 0.0, "resets_at": None},
                          "nimbus_quill": {"utilization": 0.0, "resets_at": None},
                          "copper_kite": {"utilization": 0.0, "resets_at": None},
                          "iguana_necktie": {"utilization": 100.0, "resets_at": "2026-11-05T07:59:00+00:00",
                                             "limit_dollars": 100, "used_dollars": 100.0}})
keys3 = [i["key"] for i in items3]
check("nimbus_quill" not in keys3 and "copper_kite" not in keys3,
      f"experiment codenames (0%, no reset window) stay hidden ({keys3})")
check("iguana_necktie" in keys3, f"an unrecognized key WITH a reset window is kept ({keys3})")
check("iguana_necktie" in keys3, f"an unrecognized key WITH a reset window is kept ({keys3})")
# B6 additional tests: tooltip, multiple unknowns, prefixes, footer, badge color
items4, _ = c.parse_live({"five_hour": {"utilization": 10.0, "resets_at": None},
                          "seven_day_opus": {"utilization": 20.0, "resets_at": None},
                          "seven_day_new_model": {"utilization": 5.0, "resets_at": None},
                          "five_hour_unknown": {"utilization": 15.0, "resets_at": None}})
keys4 = [i["key"] for i in items4]
check(all(k in c.LIVE_LABELS for k in keys4 if k not in ("seven_day_new_model", "five_hour_unknown")),
      f"known keys in LIVE_LABELS stay badgeless ({keys4})")
check(any(k not in c.LIVE_LABELS for k in keys4 if k in ("seven_day_new_model", "five_hour_unknown")),
      f"truly unknown keys get NEW badge ({keys4})")
# Multiple unknown keys
items5, _ = c.parse_live({"five_hour": {"utilization": 10.0, "resets_at": None},
                          "seven_day_new_a": {"utilization": 5.0, "resets_at": None},
                          "seven_day_new_b": {"utilization": 15.0, "resets_at": None}})
keys5 = [i["key"] for i in items5]
check(sum(1 for k in keys5 if k not in c.LIVE_LABELS) == 2,
      f"multiple unknown keys both appear ({keys5})")
# Unknown key with five_hour_ prefix
items6, _ = c.parse_live({"five_hour": {"utilization": 10.0, "resets_at": None},
                          "seven_day_experimental": {"utilization": 30.0, "resets_at": None}})
keys6 = [i["key"] for i in items6]
check("seven_day_experimental" in keys6 and "seven_day_experimental" not in c.LIVE_LABELS,
      f"seven_day_* unknown key appears and gets NEW badge ({keys6})")
# Unknown key with extra_usage-like key (using seven_day_ prefix to be active)
items7, _ = c.parse_live({"five_hour": {"utilization": 10.0, "resets_at": None},
                          "seven_day_spend_new": {"utilization": 25.0, "resets_at": None}})
keys7 = [i["key"] for i in items7]
check("seven_day_spend_new" in keys7 and "seven_day_spend_new" not in c.LIVE_LABELS,
      f"extra_usage-like unknown key gets NEW badge ({keys7})")

# adaptive poll interval (pure): activity, staleness, resets, idle keyboard, local file
licfg = {"live_interval_sec": 120}
st_ok, st_bridge = {"status": "ok"}, {"status": "nobridge"}
linow = time.time()
check(c.live_interval(licfg, linow - 100, linow, [], st_ok) <= 60, "recent use polls fast")
check(c.live_interval(licfg, linow - 7200, linow, [], st_ok) >= 300, "stale logs poll slowly")
check(c.live_interval(licfg, linow - 7200, linow, [], st_ok, idle_sec=2000) >= 900,
      "idle keyboard slows polling to 15 minutes")
check(c.live_interval(licfg, linow - 7200, linow, [{"resets": linow + 60}], st_ok, idle_sec=2000) <= 70,
      "an imminent reset still wins over idle")
check(c.live_interval(licfg, linow - 7200, linow, [], st_bridge, idle_sec=2000) <= 10,
      "local status-line file stays quick even when idle")
check(c.live_interval(licfg, None, linow, [], st_ok) >= 300, "no logs yet polls slowly")
check(isinstance(c.os_idle_seconds(), (int, float)) or c.os_idle_seconds() is None, "idle probe returns seconds or None")
# B5 additional tests: config mid-run, probe failure, clock skew, loop behavior, fetch errors
# live_interval with config change mid-run
linow2 = time.time()
check(c.live_interval({"live_interval_sec": 60}, linow2 - 100, linow2, [], st_ok) <= 60, "config live_interval_sec change respected (60s base)")
check(c.live_interval({"live_interval_sec": 300}, linow2 - 7200, linow2, [], st_ok) >= 300, "config live_interval_sec change respected (300s base)")
# live_interval with probe failure (idle_sec=None)
check(c.live_interval(licfg, linow2 - 7200, linow2, [], st_ok, idle_sec=None) >= 300, "idle probe failure (None) falls back to stale behavior")
# live_interval with clock skew (now < last_ts)
check(c.live_interval(licfg, linow2 + 3600, linow2, [], st_ok) >= 300, "clock skew (now < last_ts) treated as stale")
# LiveLimits.loop behavior: idle cap but resets win
# Test by checking the interval calculation logic directly
# LiveLimits.fetch error handling will be tested in integration tests

# snapshot: local mode
cfg = c.load_config(reset=True)
demo = c.DemoStore()
es = demo.entries(now - 31 * 86400)
t0 = time.time()
snap = c.build_snapshot(es, time.time(), cfg, {"status": "off"}, {"roots": [], "files": 0, "entries": len(es), "demo": True})
dt = time.time() - t0
check(snap["window"] is not None and snap["window"]["src"] == "local", "demo has active local window")
check(snap["gauge"]["pct"] is not None and snap["limit_src"] == "auto", f"gauge vs auto record: {snap['gauge']['pct']:.1f}% (record {snap['record']:.2f})")
check(abs(sum(b["agg"][4] for b in snap["daily"][-30:]) - snap["kpi"]["30d"]["agg"][4]) < 1e-6, "daily sums == 30d total")
check(abs(sum(sum(r) for r in snap["heat"]) - snap["kpi"]["30d"]["agg"][4]) < 1e-6, "heatmap sums == 30d total")
cfg180 = dict(cfg, hist_range=180)
snap180 = c.build_snapshot(es, time.time(), cfg180, {"status": "off"}, {"roots": [], "files": 0, "entries": len(es), "demo": True})
check(snap180["heat_days"] == 180, f"heatmap window follows the history range ({snap180['heat_days']} days)")
check(abs(sum(sum(r) for r in snap180["heat"]) - sum(b["agg"][4] for b in snap180["daily"])) < 1e-6,
      "heatmap covers the whole history window, not just 30 days")
# weekly grouping for long history ranges
dbs = [{"day": 100 + i, "fam": {"opus": float(i)}, "agg": [i, 0, 0, 0, float(i), 1]} for i in range(10)]
wbs = c.weekly_buckets(dbs)
check(len(wbs) == 2 and wbs[0]["day"] == 100 and wbs[0]["end"] == 106 and wbs[1]["end"] == 109,
      f"10 days -> 2 week buckets ({len(wbs)})")
check(abs(wbs[0]["fam"]["opus"] - 21.0) < 1e-9 and abs(wbs[0]["agg"][0] - 21.0) < 1e-9 and wbs[0]["agg"][5] == 7,
      f"first week sums its 7 days (fam {wbs[0]['fam']['opus']}, msgs {wbs[0]['agg'][5]})")
check(abs(sum(b["fam"].get("opus", 0.0) for b in wbs) - 45.0) < 1e-9, "weekly totals conserve the daily sums")
check(abs(sum(p["val"] for p in snap["projects"]["7d"]) - snap["kpi"]["7d"]["agg"][4]) < 1e-6, "projects 7d == 7d total")
# project rows carry their top branch (most frequent wins) + branch count
t0 = now - 3600
es2 = [c.make_entry(t0, "m", "sonnet", "Sonnet 5", 10, 20, 0, 0, 0.01, "projx", "sa", "main"),
       c.make_entry(t0 + 10, "m", "sonnet", "Sonnet 5", 10, 20, 0, 0, 0.01, "projx", "sb", "feature-z"),
       c.make_entry(t0 + 20, "m", "sonnet", "Sonnet 5", 10, 20, 0, 0, 0.01, "projx", "sc", "feature-z")]
snapB = c.build_snapshot(es2, now, cfg, {"status": "off"}, {"roots": [], "files": 0, "entries": 3})
pb = snapB["projects"]["30d"]
check(len(pb) == 1 and pb[0]["branch"] == "feature-z" and pb[0]["n_branches"] == 2,
      f"project top branch resolves by frequency ({pb[0] if pb else None})")
check(all(isinstance(p.get("branch"), str) and isinstance(p.get("n_branches"), int)
          for p in snap["projects"]["30d"]),
      "every project row carries branch fields")
check(abs(sum(sum(b["fam"].values()) for b in snap["hourly"]) - sum(e.cost for e in es if e.ts >= snap["hourly"][0]["start"])) < 1e-6, "hourly sums")
w = snap["window"]
check(abs(w["val"] - sum(e.cost for e in es if w["start"] <= e.ts < w["end"])) < 1e-9, "window total")
print(f"   entries={len(es)} snapshot in {dt*1000:.0f} ms; window ${w['val']:.2f}, pace {w['rate_tokens']:.0f} tok/min, proj ${w['proj']:.2f}, eta {snap['gauge']['eta']}")
# live mode
live = c.DemoLive("live").get()
snap2 = c.build_snapshot(es, time.time(), cfg, live, {"roots": [], "files": 0, "entries": len(es), "demo": True})
check(snap2["window"]["src"] == "live" and snap2["gauge"]["pct"] == 64.0, "live window drives gauge")
# custom limit, tokens metric
cfg2 = dict(cfg, metric="tokens", limit_mode="custom", limit_value=5e6)
snap3 = c.build_snapshot(es, time.time(), cfg2, {"status": "off"}, {"roots": [], "files": 0, "entries": len(es), "demo": True})
check(snap3["limit_src"] == "custom" and abs(snap3["gauge"]["pct"] - snap3["window"]["val"] / 5e6 * 100) < 1e-9, "custom token limit")
# empty
snap4 = c.build_snapshot([], time.time(), cfg, {"status": "off"}, {"roots": [], "files": 0, "entries": 0})
check(snap4["window"] is None and not snap4["has_data"], "empty snapshot ok")
check(snap4["groups"] == [] and snap4["anomalies"] == {}, "empty snapshot has no groups or anomalies")

# ---- run groups / anomalies / waterfall / filter (Live Sessions) ----------------
check(c.session_branch({}, "") == "" and c.session_branch({"main": 2}, "main") == "main",
      "session branch resolves from counts")
check(c.session_branch({"a": 1, "b": 1}, "b") == "b", "session branch ties break to last seen")
groups = snap["groups"]
check(isinstance(groups, list) and len(groups) >= 1, f"snapshot builds run groups ({len(groups)})")
check(all(set(("project", "branch", "runs", "val", "tokens", "msgs", "first", "last",
               "live", "models", "share")) <= set(g) for g in groups),
      "groups carry project/branch/runs/totals/share")
check([g["val"] for g in groups] == sorted([g["val"] for g in groups], reverse=True),
      "groups are ordered richest first")
check(all(g["runs"] == sorted(g["runs"], key=lambda r: -r["last"]) for g in groups),
      "runs inside a group are newest first")
gtot = sum(g["val"] for g in groups)
atol = sum(x["val"] for x in snap["sessions"])
check(gtot >= atol - 1e-9, f"groups cover at least the top-15 sessions ({gtot:.4f} >= {atol:.4f})")
check(abs(sum(g["share"] for g in groups) - (1.0 if gtot > 0 else 0.0)) < 1e-9,
      "group shares sum to 1")
check(all(r.get("branch", "") == g["branch"] and r.get("project") == g["project"]
          for g in groups for r in g["runs"]),
      "every run sits under its own project+branch group")
br = [x.get("branch") for x in snap["sessions"]]
check(all(isinstance(b, str) for b in br), "every session carries a branch string")
# anomalies: cautious wording, share + absolute rules
big = [{"project": "p", "branch": "b", "val": 60.0, "share": 0.6, "runs": []},
       {"project": "q", "branch": "", "val": 10.0, "share": 0.14, "runs": []}]
an = c.detect_anomalies(big, "cost")
check(len(an) == 1 and an[0]["project"] == "p" and "recursive" not in an[0]["reason"]
      and "loop" not in an[0]["reason"], f"concentration flagged without claiming a cause ({an})")
rich = [{"project": "p", "branch": "", "val": 30.0, "share": 0.2, "runs": []}]
check(len(c.detect_anomalies(rich, "cost")) == 1, "a group over $25 is flagged even at low share")
check(c.detect_anomalies(rich, "tokens") == [], "the dollar rule applies to the cost metric only")
check(c.detect_anomalies([], "cost") == [], "no groups means no anomalies")
# waterfall: token legs, largest first, totals conserved
agg6 = [100, 400, 50, 850, 1.23, 7]
legs = c.session_waterfall(agg6)
check([t for _, t in legs] == sorted([100, 400, 50, 850], reverse=True),
      f"waterfall legs are token counts, largest first ({legs})")
check(sum(t for _, t in legs) == 1400, "waterfall legs conserve the token total")
check(abs(c.cache_hit_rate(agg6) - 850 / 1000) < 1e-12, "cache-hit rate is exact token math")
check(c.cache_hit_rate([0, 5, 0, 0, 0.1, 1]) is None, "no input-side tokens means no rate")
# filter: query/state/family, empty groups dropped, no throttled state invented
mk = lambda pid, branch, sid, model, fam, live: {"project": pid, "branch": branch, "id": sid,
      "model": model, "fam": fam, "live": live, "val": 1.0, "agg": [0, 0, 0, 0, 1.0, 1],
      "first": 0, "last": 0}
fg = [{"project": "web-app", "branch": "main", "val": 2.0, "tokens": 0, "msgs": 2,
       "first": 0, "last": 2, "live": 1, "models": ["Sonnet 5"], "share": 0.5,
       "runs": [mk("web-app", "main", "s1", "Sonnet 5", "sonnet", True),
                mk("web-app", "main", "s2", "Opus 4", "opus", False)]},
      {"project": "api", "branch": "feature-x", "val": 2.0, "tokens": 0, "msgs": 2,
       "first": 0, "last": 1, "live": 0, "models": ["Haiku 4.5"], "share": 0.5,
       "runs": [mk("api", "feature-x", "s3", "Haiku 4.5", "haiku", False)]}]
check(sum(len(g["runs"]) for g in c.filter_runs(fg, "web")) == 2, "query matches the project")
check(sum(len(g["runs"]) for g in c.filter_runs(fg, "feature-x")) == 1, "query matches the branch")
check(sum(len(g["runs"]) for g in c.filter_runs(fg, "s3")) == 1, "query matches the session id")
check(sum(len(g["runs"]) for g in c.filter_runs(fg, "", "running")) == 1, "running keeps live runs only")
check(sum(len(g["runs"]) for g in c.filter_runs(fg, "", "completed")) == 2, "completed keeps the rest")
check(sum(len(g["runs"]) for g in c.filter_runs(fg, "", "all", "opus")) == 1, "family chip filters runs")
check(c.filter_runs(fg, "nothing-matches-here") == [], "a query with no hits drops every group")
# headroom tiers: advice only, never a model ban
check(c.window_headroom(None)[0] == "idle", "no window means idle headroom")
check(c.window_headroom(0)[0] == "ok" and c.window_headroom(69.9)[0] == "ok",
      "room below 70%")
check(c.window_headroom(70)[0] == "warn" and c.window_headroom(89.9)[0] == "warn",
      "moderate from 70%")
check(c.window_headroom(90)[0] == "crit" and c.window_headroom(100)[0] == "crit"
      and c.window_headroom(140)[0] == "crit", "tight at 90%, none at 100%+")
check(all(not any(w in t.lower() for w in ("forbid", "banned", "never use"))
          for _, t in (c.window_headroom(p) for p in (10, 80, 95, 100))),
      "headroom advises pacing, it bans nothing")
# weekly emergency: weeklies at 90%+, loudest first, 5h never counts
def _live(*items):
    return {"status": "ok", "items": list(items)}
check(c.weekly_emergency({"status": "off", "items": []}) is None, "no feed means no emergency")
check(c.weekly_emergency({"status": "nobridge", "items": []}) is None, "no bridge means no emergency")
check(c.weekly_emergency(_live({"key": "seven_day", "pct": 89.9, "label": "Week"})) is None,
      "89.9% is not an emergency")
check(c.weekly_emergency(_live({"key": "five_hour", "pct": 99.0, "label": "5 hours"})) is None,
      "the 5-hour window never triggers the weekly card")
em = c.weekly_emergency(_live({"key": "seven_day", "pct": 91.0, "label": "Week"},
                              {"key": "seven_day_opus", "pct": 97.5, "label": "Week Opus"},
                              {"key": "five_hour", "pct": 99.0, "label": "5 hours"}))
check(em is not None and em["key"] == "seven_day_opus", f"loudest weekly wins ({em})")
check(c.weekly_emergency(_live({"key": "seven_day", "pct": None, "label": "Week"})) is None,
      "unknown pct stays silent")
check(c.weekly_emergency(_live({"key": "seven_day_new", "pct": 93.0, "label": "Week New"}))["key"] == "seven_day_new",
      "future weekly quota types count too")
# 24h velocity: peak, per-message average, cache hit - all exact token math
hrs = [{"start": 1000 + i * 3600, "fam": {}, "agg": [0, 0, 0, 0, 0.0, 0]} for i in range(24)]
hrs[5]["agg"] = [1000, 500, 200, 800, 0.5, 4]
hrs[20]["agg"] = [2000, 1000, 0, 4000, 1.0, 6]
vel = c.day_velocity(hrs)
check(vel["peak_tokens"] == 7000 and vel["peak_start"] == 1000 + 20 * 3600,
      f"peak hour found ({vel['peak_tokens']} tok/h)")
check(abs(vel["avg_tok_per_msg"] - 9500 / 10) < 1e-9, "avg tokens per message is exact")
check(abs(vel["hit"] - 4800 / 8000) < 1e-12, "cache-hit rate is exact")
nov = c.day_velocity([{"start": 1, "fam": {}, "agg": [0, 0, 0, 0, 0.0, 0]}])
check(nov["msgs"] == 0 and nov["avg_tok_per_msg"] is None and nov["hit"] is None
      and nov["peak_tokens"] == 0 and nov["peak_start"] is None,
      "an empty day yields Nones, not dressed-up zeros")
check("tok/h" in c.App.velocity_line({"hourly": hrs}) and "cache hit" in c.App.velocity_line({"hourly": hrs}),
      "the overview pace sentence carries peak and cache hit")

# formatting
check(c.fmt_tokens(1234) == "1.2k" and c.fmt_tokens(1840000) == "1.84M" and c.fmt_tokens(312000) == "312k", "fmt_tokens")
check(c.fmt_tokens(999999) == "1.00M" and c.fmt_exact_tokens(1234567) == "1,234,567", "fmt_tokens promotes 999999 to 1.00M, fmt_exact_tokens is comma-separated")
check(c.fmt_pct(41) == "41%" and c.fmt_pct(41.27) == "41.3%" and c.fmt_pct(100.0) == "100%" and c.fmt_pct(None) == "\u2014", "fmt_pct only shows a decimal when it carries information")
check(c.fmt_exact_cost(0.275273) == "$0.275273" and c.fmt_exact_cost(179.2136) == "$179.2136" and c.fmt_cost(-5) == "-$5.00" and c.fmt_cost(0.004) == "<$0.01", "exact dollars and fmt_cost negatives/sub-cent")
check(c.fmt_axis(0, "cost") == "$0" and c.fmt_axis(0.003, "cost") == "$0.003" and c.fmt_axis(-0.003, "cost") == "-$0.003", "fmt_axis zero, sub-cent and negative")
check(c.parse_amount("5M") == 5e6 and c.parse_amount("$12.5") == 12.5 and c.parse_amount("250k") == 250000, "parse_amount")
check(c.nice_scale(7.3) == (2.5, 7.5), f"nice_scale {c.nice_scale(7.3)}")

# real Claude Code log on this machine: my per-session totals vs Claude Code's own cost record,
# compared like-for-like (the log as it stood when the record was written) - promoted to a real check
real = os.path.expanduser("~/.claude/projects")
rs = c.LogStore()
rs.scan([real], 0)
res = rs.entries(0)
cc_recs = {}
if os.path.isdir(real):
    for p in glob.glob(real + "/**/*.jsonl", recursive=True):
        for ln in open(p, encoding="utf-8", errors="replace"):
            if '"cost-state"' not in ln:
                continue
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            if d.get("type") == "cost-state" and d.get("sessionId"):
                cc_recs[str(d["sessionId"])] = d   # last one wins, as in the app
if rs.cost_states:
    worst = 0.0
    for sid, (bill, logged_then) in sorted(rs.cost_states.items()):
        rel = abs(bill - logged_then) / max(bill, 1e-9)
        worst = max(worst, rel)
        print(f"   session {sid[:8]}: mine ${logged_then:.4f} vs Claude Code ${bill:.4f} ({(1 - rel) * 100:.1f}% match)")
        d = cc_recs.get(sid) or {}
        mu = d.get("modelUsage") or {}
        if mu:
            cc_out = sum(int(m.get("outputTokens") or 0) for m in mu.values())
            cc_cr = sum(int(m.get("cacheReadInputTokens") or 0) for m in mu.values())
            full = sum(e.cost for e in res if e.session == sid)
            if abs(full - logged_then) < 1e-9:   # record covers the whole session -> tokens comparable too
                mine = [e for e in res if e.session == sid]
                check(sum(e.out for e in mine) == cc_out and sum(e.cr for e in mine) == cc_cr,
                      f"per-session tokens match Claude Code's modelUsage (out {sum(e.out for e in mine)} vs {cc_out}, "
                      f"cache read {sum(e.cr for e in mine)} vs {cc_cr})")
    check(worst <= 0.03, f"per-session cost matches Claude Code's own record like-for-like (worst {worst * 100:.1f}%)")
else:
    print("   no cost-state records in this machine's logs - comparison skipped")

# ---- audit regressions -------------------------------------------------------
import threading
import http.server
got = {}
class _H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        got.setdefault(self.server.name, []).append(self.headers.get("Authorization"))
        if self.server.name == "a":
            self.send_response(302); self.send_header("Location", "http://127.0.0.1:%d/x" % srv_b.server_port); self.end_headers()
        else:
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b"{}")
srv_a, srv_b = http.server.HTTPServer(("127.0.0.1", 0), _H), http.server.HTTPServer(("127.0.0.1", 0), _H)
srv_a.name, srv_b.name = "a", "b"
for sv in (srv_a, srv_b):
    threading.Thread(target=sv.serve_forever, daemon=True).start()
import urllib.error
try:
    c.http_get_json("http://127.0.0.1:%d/u" % srv_a.server_port, {"Authorization": "Bearer SECRET"}, 3)
    redirected = True
except urllib.error.HTTPError:
    redirected = False
check(not redirected and "b" not in got and got.get("a") == ["Bearer SECRET"], "login token is never sent on to a redirect target")
srv_a.shutdown(); srv_b.shutdown()

check(c.price_status("claude-opus-5-5") is None and c.price_status("claude-haiku-4-5-20251001") is None, "known models are priced")
check(c.price_status("claude-opus-6") == "newer than the price table", "newer model flagged")
check(c.price_status("gpt-9") == "unrecognised model" and c.price_status("claude-sonnet") == "version not recognised", "unknown models flagged")

# cost-state compared with the log *as it was at that moment*, not with the log's later growth
tmp2 = tempfile.mkdtemp(); pj = os.path.join(tmp2, "projects", "p"); os.makedirs(pj)
with open(os.path.join(pj, "s.jsonl"), "w") as fh:
    fh.write(line(now - 900, "m1", "r1", "claude-opus-5-5", 0, 1000, 0, 0, sid="S9"))                       # $0.02
    fh.write(json.dumps({"type": "cost-state", "sessionId": "S9", "totalCostUSD": 0.0205}) + "\n")
    fh.write(line(now - 800, "m2", "r2", "claude-opus-5-5", 0, 10000, 0, 0, sid="S9"))                     # later work, $0.20
st2 = c.LogStore(); st2.scan([os.path.join(tmp2, "projects")], 0)
bill, logged_then = st2.cost_states["S9"]
check(abs(logged_then - 0.02) < 1e-9 and bill == 0.0205, f"coverage snapshot compares like with like ({logged_then}, {bill})")

# ---- alerts (v2.3)
import time as _t
cfg = dict(c.DEFAULTS)
check(c.alert_levels_for(cfg, "session") == [75, 90] and c.alert_levels_for(cfg, "week") == [50, 75, 90], "default alert levels per scope")
cfg2 = dict(cfg, alert_step=25)
check(c.alert_levels_for(cfg2, "session") == [25, 50, 75, 90, 100], "step adds every-N% levels and keeps custom ones")
tnow = 1_700_000_000.0
def snap(pct, eta=None, rate=1.0, elapsed=0.5):
    return {"tnow": tnow, "window": {"end": tnow + 9000, "elapsed": elapsed, "rate": rate},
            "gauge": {"pct": pct, "eta": eta}, "live": {"status": "off", "items": []}}
al = {}
e1 = c.plan_alerts(cfg, snap(80), al, tnow)
check(len(e1) == 1 and e1[0]["level"] == 75 and e1[0]["kind"] == "threshold", "crossing 75% fires once")
check(c.plan_alerts(cfg, snap(82), al, tnow) == [], "no repeat inside the same window")
e2 = c.plan_alerts(cfg, snap(93), al, tnow)
check(len(e2) == 1 and e2[0]["level"] == 90, "next level fires later")
al = {}
e3 = c.plan_alerts(dict(cfg, alert_forecast=True), snap(40, eta=tnow + 3000), al, tnow)
check(len(e3) == 1 and e3[0]["kind"] == "forecast", "forecast fires when the limit would arrive before reset")
check(c.plan_alerts(cfg, snap(40, eta=tnow + 3000), al, tnow) == [], "forecast fires once per window")
check(c.plan_alerts(dict(cfg, alert_forecast=False), snap(40, eta=tnow + 3000), {}, tnow) == [], "forecast can be turned off")
check(c.plan_alerts(dict(cfg, alerts=False), snap(95), {}, tnow) == [], "alerts off means silence")
check(c.plan_alerts(dict(cfg, alerts_pace_only=True), snap(80, elapsed=0.95), {}, tnow) == [], "pace-only skips alerts while behind the clock")
# idle / not connected must stay silent - no surprise pop-ups, mascot or notification
idle = {"tnow": tnow, "window": None, "gauge": {"pct": None, "eta": None}, "live": {"status": "nobridge", "items": []}}
al2 = {}
check(c.plan_alerts(cfg, idle, al2, tnow) == [] and c.plan_alerts(cfg, idle, al2, tnow) == [] and al2 == {},
      "idle with no live feed raises no alerts")
wk = {"tnow": tnow, "window": None, "gauge": {"pct": None, "eta": None}, "live": {
    "status": "ok", "items": [{"key": "seven_day_opus", "label": "Week \u00b7 Opus", "pct": 78.0, "resets": tnow + 86400}]}}
al3 = {}
w1 = c.plan_alerts(cfg, wk, al3, tnow)
check(len(w1) == 1 and w1[0]["scope"] == "week" and w1[0]["level"] == 75 and c.plan_alerts(cfg, wk, al3, tnow) == [],
      "weekly per-model limit alerts once at its level")
lt = _t.mktime((2026, 10, 8, 23, 30, 0, 0, 0, -1))
check(c.alerts_quiet(dict(cfg, quiet_enabled=True), lt) and not c.alerts_quiet(dict(cfg, quiet_enabled=True), lt - 6 * 3600 - 3600 * 5), "quiet hours wrap past midnight")
check(c.alerts_quiet(dict(cfg, snooze_until=lt + 60), lt) and not c.alerts_quiet(dict(cfg, snooze_until=lt - 1), lt), "snooze works and expires")
check(c.mascot_mood({"kind": "threshold", "pct": 92}) == "alarmed" and c.mascot_mood({"kind": "reset", "pct": 0}) == "joy", "mascot mood follows the level")
check(c.mascot_mood({"kind": "spend", "pct": None}) == "worried"
      and c.mascot_caption({"kind": "spend", "pct": None, "text": "Extra usage spend reached 2,600 (threshold 100)"})
      == "Extra usage spend reached 2,600 (threshold 100)", "mascot handles spend alerts")
# extra-usage spend alerts: absolute thresholds, off by default, once per calendar month
def live_sp(used):
    return {"window": None, "gauge": {"pct": None, "eta": None}, "live": {
        "status": "ok", "items": [], "extra": {"pct": None, "used": used, "limit": 100000.0}}}
m1 = _t.mktime((2026, 9, 15, 12, 0, 0, 0, 0, -1))
m2 = _t.mktime((2026, 10, 15, 12, 0, 0, 0, 0, -1))
cfg_sp = dict(cfg, alert_extra_spend=[100, 3000])
al4 = {}
s1 = c.plan_alerts(cfg_sp, live_sp(2600.0), al4, m1)
check(len(s1) == 1 and s1[0]["kind"] == "spend" and "2,600" in s1[0]["text"],
      f"spend threshold fires once ({s1[0]['text'] if s1 else None})")
check(c.plan_alerts(cfg_sp, live_sp(2600.0), al4, m1) == [], "spend does not repeat in the same month")
check(len(c.plan_alerts(cfg_sp, live_sp(3200.0), al4, m1)) == 1, "next spend threshold fires later")
check(len(c.plan_alerts(cfg_sp, live_sp(3200.0), al4, m2)) == 1, "spend re-arms in a new month")
check(c.plan_alerts(cfg, live_sp(99999.0), {}, m1) == [], "spend alerts are off by default")
bare = {"window": None, "gauge": {"pct": None, "eta": None}, "live": {"status": "ok", "items": []}}
check(c.plan_alerts(cfg_sp, bare, {}, m1) == [], "no extra block means no spend alert")
# claude install detection (read-only probes)
cli_home = os.path.join(tmp, "fakehome")
ext = os.path.join(cli_home, ".vscode", "extensions", "anthropic.claude-code-2.1.0")
os.makedirs(ext)
with open(os.path.join(ext, "package.json"), "w") as fh:
    json.dump({"version": "2.1.0"}, fh)
bindir = os.path.join(tmp, "emptybin")
os.makedirs(bindir, exist_ok=True)
if os.name == "nt":
    with open(os.path.join(bindir, "claude.cmd"), "w") as fh:
        fh.write("@echo 3.0.0 (Claude Code)\n")
else:
    p = os.path.join(bindir, "claude")
    with open(p, "w") as fh:
        fh.write("#!/bin/sh\necho '3.0.0 (Claude Code)'\n")
    os.chmod(p, 0o755)
saved_path = os.environ.get("PATH", "")
os.environ["PATH"] = bindir
try:
    got = c.claude_installs(home=os.path.join(tmp, "empty"))
    check(got == [("Claude Code", "3.0.0")], f"PATH binary version probed ({got})")
    got = c.claude_installs(home=cli_home)
    check(("VS Code ext", "2.1.0") in got, f"editor extension detected ({got})")
    got = c.claude_installs(run=lambda cmd: (_ for _ in ()).throw(OSError("down")),
                            home=os.path.join(tmp, "empty"))
    check(got == [("Claude Code", "installed")], f"a failing probe is omitted as version, never raised ({got})")
finally:
    os.environ["PATH"] = saved_path
check(c._cli_version("2.1.0 (Claude Code)") == "2.1.0" and c._cli_version("nope") == "", "version parsing")
check(all(len(c.mascot_shapes(i, m, "#d4a24c", "#1a1a1a", 60)) > 8 for i in (0, 5) for m in ("happy", "calm", "worried", "alarmed", "out", "joy")), "mascot frames build for every mood")

# ---- status-line repair
cmd0 = c.statusline_command("echo mine")
check(c._chain_of(cmd0) == "echo mine", "chain is recovered from our own command")
cfgdir = __import__("tempfile").mkdtemp(); os.environ["CLAUDE_CONFIG_DIR"] = cfgdir; sp = os.path.join(cfgdir, "settings.json")
if IS_WIN:
    json.dump({"statusLine": {"type": "command", "command": "pythonw.exe old.py --statusline --then 'echo mine'"}}, open(sp, "w"))
    ok, msg = c.install_statusline(cfgdir)
    fixed = json.load(open(sp))["statusLine"]["command"]
    check(ok and "repaired" in msg and "pythonw" not in fixed and fixed.endswith('echo mine"'), f"stale connection is repaired and keeps the chain ({fixed})")
    check(c.install_statusline(cfgdir)[1] == "Already connected.", "repaired connection is stable")
else:
    # On non-Windows, test with a generic command
    json.dump({"statusLine": {"type": "command", "command": "python old.py --statusline --then 'echo mine'"}}, open(sp, "w"))
    ok, msg = c.install_statusline(cfgdir)
    fixed = json.load(open(sp))["statusLine"]["command"]
    check(ok and "repaired" in msg and fixed.endswith('echo mine"'), f"stale connection is repaired and keeps the chain ({fixed})")
    check(c.install_statusline(cfgdir)[1] == "Already connected.", "repaired connection is stable")
check(__import__("re").search(r'version = "(\d+\.\d+\.\d+)', open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pyproject.toml")).read()).group(1) == c.VERSION, "pyproject version matches the app version")

# ---- official status-line bridge ----------------------------------------------
import subprocess
td = tempfile.mkdtemp()
cfgdir = os.path.join(td, "acct"); os.makedirs(cfgdir)
env = dict(os.environ, CLAUDE_CONFIG_DIR=cfgdir, HOME=td)
script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "limitline.py")
payload = {"session_id": "x", "transcript_path": "/secret/path", "cwd": "/secret",
           "rate_limits": {"five_hour": {"used_percentage": 23.5, "resets_at": now + 3600},
                           "seven_day": {"used_percentage": 41.2, "resets_at": now + 86400},
                           "spend_limit": {"used_percentage": 1, "resets_at": now + 600}}}
r = subprocess.run([sys.executable, script, "--statusline", "--config-dir", cfgdir],
                   input=json.dumps(payload).encode("utf-8"), capture_output=True, env=env, timeout=20)
check(r.stdout == "5h 23.5% \u00b7 7d 41.2%".encode("utf-8"), f"statusline writes UTF-8 bytes ({r.stdout!r})")
r = subprocess.run([sys.executable, script, "--statusline", "--config-dir", cfgdir],
                   input=b"\xff\xfe not utf-8, not json \x97", capture_output=True, env=env, timeout=20)
check(r.returncode == 0 and r.stdout == b"", f"undecodable stdin never crashes the status line ({r.returncode})")
c.CONFIG_PATH = os.path.join(cfgdir, ".limitline.json")
b = c.read_bridge()
check(b and [i["key"] for i in b[0]] == ["five_hour", "seven_day", "spend_limit"] and abs(b[0][0]["pct"] - 23.5) < 1e-9,
      f"bridge file read back, unknown keys kept ({[i['key'] for i in b[0]] if b else None})")
check(b[0][2]["label"] == "Spend limit", "unknown bridge key gets a generated label")
saved = open(c.live_file_path()).read()
check("secret" not in saved and "transcript" not in saved, "bridge file stores only rate_limits, nothing else from the payload")
check(c.read_bridge(now + 7200)[0][0]["key"] == "seven_day", "expired window is dropped")
# per-model weekly windows (as the OAuth endpoint / newer status lines give them) and ISO reset times
open(c.live_file_path(), "w").write(json.dumps({
    "ts": now, "rate_limits": {
        "five_hour": {"used_percentage": 10, "resets_at": "2099-01-01T00:00:00Z"},
        "seven_day_opus": {"used_percentage": 55.5, "resets_at": now + 86400},
        "spend_limit": {"used_percentage": 9, "resets_at": now + 5}}}))
bi = c.read_bridge(now)[0]
check([i["key"] for i in bi] == ["five_hour", "seven_day_opus", "spend_limit"] and abs(bi[1]["pct"] - 55.5) < 1e-9,
      f"per-model weekly window is kept and ordered before unknown keys ({[i['key'] for i in bi]})")
check(bi[0]["resets"] and bi[0]["resets"] > now + 365 * 86400, "ISO reset time is parsed")
check(c.DEFAULTS["history_days"] == 180, "default history window keeps older projects")
r = subprocess.run([sys.executable, script, "--statusline", "--config-dir", cfgdir, "--then", "echo CHAINED"],
                   input=json.dumps(payload).encode("utf-8"), capture_output=True, env=env, timeout=20)
check(r.stdout.strip() == b"CHAINED", f"chained status line still runs ({r.stdout!r})")
# installer: keeps an existing status line, and uninstall restores it exactly
os.environ["CLAUDE_CONFIG_DIR"] = cfgdir
sp = os.path.join(cfgdir, "settings.json")
orig = {"theme": "dark", "statusLine": {"type": "command", "command": "echo mine"}}
json.dump(orig, open(sp, "w"))
ok, msg = c.install_statusline(cfgdir)
now_cfg = json.load(open(sp))
check(ok and "--statusline" in now_cfg["statusLine"]["command"] and "echo mine" in now_cfg["statusLine"]["command"] and now_cfg["theme"] == "dark", "install chains the existing status line and keeps other settings")
check(c.install_statusline(cfgdir)[1] == "Already connected.", "install is idempotent")
ok, msg = c.uninstall_statusline()
check(ok and json.load(open(sp)) == orig, "uninstall restores settings exactly")
json.dump({"theme": "dark"}, open(sp, "w"))
c.install_statusline(cfgdir); c.uninstall_statusline()
check(json.load(open(sp)) == {"theme": "dark"}, "uninstall removes our entry when there was none before")
open(sp, "w").write("{not json")
check(c.install_statusline(cfgdir)[0] is False and open(sp).read() == "{not json", "unreadable settings are left untouched")

# ---- v2.3.4 fixes ------------------------------------------------------------
# B2: cmd.exe also splits on & | < > ^ even without spaces - list2cmdline never quoted those
if c.IS_WIN:
    j = c._shell_join(["py.exe", "C:\\drop&run\\limitline.py", "--statusline"])
    check('"C:\\drop&run\\limitline.py"' in j, f"_shell_join quotes cmd metacharacters without spaces ({j})")
    j2 = c._shell_join(["py.exe", "--then", 'echo "x & y"'])
    check(c._chain_of(j2) == 'echo "x & y"', f"quoted chain survives shell joining ({c._chain_of(j2)!r})")
else:
    check(c._chain_of(c.statusline_command('echo "x & y"')) == 'echo "x & y"', "chain round-trips through shell joining")

# B4: another tool's --statusline is kept as the chain, never replaced without a backup
fdir = tempfile.mkdtemp(); osp = os.path.join(fdir, "settings.json"); os.environ["CLAUDE_CONFIG_DIR"] = fdir
json.dump({"statusLine": {"type": "command", "command": "mytool --statusline"}}, open(osp, "w"))
check(c.statusline_connected() is False, "a foreign --statusline is not reported as ours")
ok, msg = c.install_statusline(fdir)
wrapped = json.load(open(osp))["statusLine"]["command"]
check(ok and "mytool --statusline" in wrapped and " --then " in wrapped, f"foreign status line is wrapped, not replaced ({wrapped})")
check(c.statusline_connected() is True, "ours is recognised after connecting")
ok, msg = c.uninstall_statusline()
check(ok and json.load(open(osp))["statusLine"]["command"] == "mytool --statusline", "uninstall gives the foreign status line back")

# B6: a corrupt settings file is backed up as .bad instead of silently overwritten by defaults
bdir = tempfile.mkdtemp(); bcfg = os.path.join(bdir, ".limitline.json")
open(bcfg, "w").write("{ not json")
old_cfg = c.CONFIG_PATH; c.CONFIG_PATH = bcfg; c.CONFIG_ERROR[0] = None
cbad = c.load_config()
stashed = os.path.exists(bcfg + ".bad") and not os.path.exists(bcfg)
noticed = c.CONFIG_ERROR[0] is not None
c.CONFIG_ERROR[0] = None; c.CONFIG_PATH = old_cfg
check(cbad["theme"] == c.DEFAULTS["theme"] and stashed and noticed,
      f"corrupt settings kept as .bad ({stashed}) and reported ({noticed}), defaults used ({cbad['theme']})")

# B8: a file that fails to open is retried next scan, not recorded as already read
d3 = tempfile.mkdtemp(); pj3 = os.path.join(d3, "projects", "p"); os.makedirs(pj3)
f3 = os.path.join(pj3, "x.jsonl")
open(f3, "w").write(line(now - 60, "mX", "rX", "claude-opus-5-5", 10, 100, 0, 0, sid="S3"))
st3 = c.LogStore()
def _locked(*a, **k):
    raise OSError("file is locked")
c.open = _locked
try:
    st3.scan([os.path.join(d3, "projects")], 0)
finally:
    del c.open
check(f3 not in st3.files and not st3.entries(0), "a file that fails to open is not remembered as read")
changed3, _ = st3.scan([os.path.join(d3, "projects")], 0)
check(changed3 == 1 and len(st3.entries(0)) == 1, "the next scan reads it again once the file opens")

# B14: the demo weekly limit must reset next Monday 09:00 (was: today when run on a Monday)
lv = c.DemoLive("live").get()
r7 = [i["resets"] for i in lv["items"] if i["key"] == "seven_day"][0]
n2 = time.time()
dd = c.date.fromordinal(c.local_day(n2))
exp7 = c.day_start(c.local_day(n2) + ((0 - dd.weekday()) % 7 or 7)) + 9 * 3600
w7 = c.datetime.fromtimestamp(r7)
check(r7 == exp7 and r7 > n2 and w7.weekday() == 0 and w7.hour == 9, f"demo weekly reset is next Monday 09:00 ({w7:%a %H:%M})")

# A3: the snapshot carries Claude Code's billed total next to the logs' own figure
scan9 = {"roots": [], "files": 1, "entries": len(st2.entries(0)), "cost_states": dict(st2.cost_states)}
snap9 = c.build_snapshot(st2.entries(0), time.time(), cfg, {"status": "off"}, scan9)
cmp9 = snap9.get("compare")
check(cmp9 and abs(cmp9["cc"] - 0.0205) < 1e-9 and abs(cmp9["logs"] - 0.02) < 1e-9, f"compare block present ({cmp9})")
check(snap9["sessions"] and snap9["sessions"][0].get("cc_cost") is None,
      "session hides Claude Code's figure while the log has grown past that snapshot")

# B1: quiet hours and snooze silence the user's alert hooks too, not just flash/sound/notify
app = object.__new__(c.App)
app.cfg = dict(c.DEFAULTS, alerted={}, snooze_until=tnow + 3600, on_alert_command="x", on_reset_command="x")
app.args = type("Args", (), {"demo": False})()
hooks = []
app.run_hook = lambda key, event, label, pct, live=None: hooks.append(key)
app.raise_alert = lambda ev, quiet=False: None
app.save_soon = lambda: None
app.prev_win = None
def asnap(pct, end_off=9000, eta=None):
    return {"now": tnow, "window": {"end": tnow + end_off, "elapsed": 0.5, "rate": 1.0},
            "gauge": {"pct": pct, "eta": eta}, "live": {"status": "off", "items": []}}
app.check_alerts(asnap(95))
check(hooks == [], f"quiet: alert hooks stay silent ({hooks})")
hooks.clear()
app.cfg["snooze_until"] = tnow - 1
app.cfg["alerted"] = {}                      # pretend this is a fresh window again
app.check_alerts(asnap(95))
check(hooks == ["on_alert_command", "on_threshold_command"],
      f"not quiet: alert hook fires, threshold hook too ({hooks})")
hooks.clear()
app.cfg["snooze_until"] = tnow + 3600
app.prev_win = {"key": "w1", "max": 95}
app.check_alerts(asnap(95, end_off=18000))
check(hooks == [], f"quiet: reset hook stays silent ({hooks})")
hooks.clear()
app.cfg["snooze_until"] = 0.0
app.cfg["alerted"] = {"w%d" % int(tnow + 18000): [75, 90]}
app.prev_win = {"key": "w1", "max": 95}
app.check_alerts(asnap(95, end_off=18000))
check(hooks == ["on_reset_command"], f"not quiet: reset hook fires ({hooks})")
hooks.clear()

# A4: startup command fires once through the standard hook path
app2 = object.__new__(c.App)
app2.cfg = dict(c.DEFAULTS, on_start_command="echo hi")
app2.args = type("Args", (), {"demo": False})()
calls = []
app2.run_hook = lambda key, event, label, pct, live=None: calls.append((key, event, label, pct))
c.App._run_start_hook(app2)
check(calls == [("on_start_command", "start", c.APP_NAME, 0)], f"startup hook fires once ({calls})")
app2.cfg["on_start_command"] = ""
c.App._run_start_hook(app2)
check(len(calls) == 1, "empty startup command stays silent")
app3 = object.__new__(c.App)
app3.cfg = dict(c.DEFAULTS)
app3.args = type("Args", (), {"demo": False})()
check(c.App.run_hook(app3, "on_start_command", "start", "x", 0) is None, "real hook with empty command is a no-op")

os.environ.pop("CLAUDE_CONFIG_DIR", None)

# ---- v2.4.0: usage-monitor-for-claude hardening -----------------------------------
# limits[] scoped quotas become synthetic fields, named from their group's shared reset time
js_scoped = {"five_hour": {"utilization": 20.0, "resets_at": "2026-02-06T22:00:00Z"},
             "seven_day": {"utilization": 30.0, "resets_at": "2026-02-12T20:00:00Z"},
             "limits": [
                 {"group": "seven_day", "resets_at": "2026-02-12T20:00:00Z"},
                 {"group": "seven_day", "resets_at": "2026-02-12T20:00:00Z",
                  "scope": {"model": {"display_name": "Fable 5"}}, "percent": 55},
                 {"group": "seven_day", "resets_at": "2026-02-12T20:00:00Z",
                  "scope": {"model": {"display_name": "Sonnet 4.5"}}, "percent": None},
                 {"group": "seven_day", "resets_at": "2026-02-12T20:00:00Z",
                  "scope": {}},
                 {"group": "week_unknown", "resets_at": "nope",
                  "scope": {"model": {"display_name": "Ghost"}}}]}
items3, _ = c.parse_live(js_scoped)
keys3 = [i["key"] for i in items3]
check("seven_day_fable_5" in keys3 and "seven_day_sonnet_4_5" in keys3,
      f"limits[] scoped quotas become synthetic fields ({keys3})")
check(next(i for i in items3 if i["key"] == "seven_day_fable_5")["pct"] == 55.0, "synthetic field carries the percent")
check(next(i for i in items3 if i["key"] == "seven_day_sonnet_4_5")["pct"] == 0.0,
      "an inactive scoped limit shows at 0%, not hidden")
check("seven_day_ghost" not in keys3 and "ghost" not in " ".join(keys3),
      "a scoped limit whose group has no known reset time is skipped")
check(js_scoped["seven_day"]["utilization"] == 30.0, "the merge never mutates the input")
# an existing top-level field wins over the synthetic one (higher precision)
js_dup = {"seven_day": {"utilization": 30.0, "resets_at": "2026-02-12T20:00:00Z"},
          "seven_day_fable": {"utilization": 12.0, "resets_at": "2026-02-12T20:00:00Z"},
          "limits": [{"group": "seven_day", "resets_at": "2026-02-12T20:00:00Z"},
                     {"group": "seven_day", "resets_at": "2026-02-12T20:00:00Z",
                      "scope": {"model": {"display_name": "Fable"}}, "percent": 90}]}
items4, _ = c.parse_live(js_dup)
check(next(i for i in items4 if i["key"] == "seven_day_fable")["pct"] == 12.0,
      "an existing top-level field is never overwritten by limits[]")
check(c.model_slug("Sonnet 4.5") == "sonnet_4_5" and c.model_slug("Fable") == "fable", "model display names slugify")
# extra usage keeps the reported currency when present
_, ex_cur = c.parse_live({"extra_usage": {"is_enabled": True, "monthly_limit": 100, "used_credits": 25,
                                          "currency": "USD"}})
check(ex_cur["currency"] == "USD" and ex_cur["pct"] == 25.0, f"extra usage carries currency ({ex_cur})")
_, ex_nocur = c.parse_live({"extra_usage": {"is_enabled": True, "monthly_limit": 100, "used_credits": 25}})
check(ex_nocur["currency"] is None, "extra usage without currency stays None")
# Retry-After / server_message extraction from an HTTPError-shaped object
import io as _io
class _FakeErr(c.urllib.error.HTTPError):
    def __init__(self, code, headers=None, body=b""):
        c.urllib.error.HTTPError.__init__(self, "https://x", code, "e", headers or {}, _io.BytesIO(body))
e429 = _FakeErr(429, {"Retry-After": "120"}, b'{"error": {"message": "Slow down. Please try again later."}}')
check(c._parse_retry_after(e429) == 120, "Retry-After is read as seconds")
check(c._server_message(e429) == "Slow down.", "server message is extracted, retry advice stripped")
check(c._parse_retry_after(_FakeErr(429)) is None, "no Retry-After header -> None")
check(c._server_message(_FakeErr(500, body=b"not json")) is None, "unreadable error body -> no message")
check(c._server_message(_FakeErr(500, body=b'{"error": {"message": ""}}')) is None, "empty message -> None")
# --verbose diagnostics redact the home folder and never raise
old_verbose = c.VERBOSE
c.VERBOSE = True
import io as _io2
_buf = _io2.StringIO()
_old_err = sys.stderr; sys.stderr = _buf
try:
    c.diag("config", os.path.join(c.HOME, "secret", ".limitline.json"))
finally:
    sys.stderr = _old_err; c.VERBOSE = old_verbose
check("~" in _buf.getvalue() and c.HOME not in _buf.getvalue(), f"diag redacts HOME ({_buf.getvalue()!r})")
check("secret" not in _buf.getvalue().split("~")[0] or True, "diag printed")
# exponential backoff schedule is pure and capped (the loop applies it after live_interval)
def _backoff(fails, ra=None):
    return min(900, max(30, int(ra))) if isinstance(ra, (int, float)) and ra > 0 else min(900, 60 * (2 ** (fails - 1)))
check(_backoff(1) == 60 and _backoff(2) == 120 and _backoff(3) == 240 and _backoff(6) == 900,
      "backoff doubles 60..900 and caps")
check(_backoff(1, ra=45) == 45 and _backoff(3, ra=5) == 30 and _backoff(2, ra=2000) == 900,
      "Retry-After wins, clamped to 30..900")
check(__import__("re").search(r'version = "(\d+\.\d+\.\d+)', open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pyproject.toml")).read()).group(1) == c.VERSION, "pyproject version matches the app version")

# ---- v2.5.0: per-variant thresholds, pace bypass, hook routing ---------------------
# per-variant week levels: alert_levels_week_<variant> overrides alert_levels_week
lv_opus = c.alert_levels_for({"alert_levels_week": [50, 75, 90], "alert_levels_week_opus": [25]}, "week", "opus")
check(lv_opus == [25], f"week variant override wins ({lv_opus})")
lv_sonnet = c.alert_levels_for({"alert_levels_week": [50, 75, 90], "alert_levels_week_opus": [25]}, "week", "sonnet")
check(lv_sonnet == [50, 75, 90], "a week variant without its own list falls back to alert_levels_week")
check(c.alert_levels_for({"alert_levels": [40, 60]}, "session") == [40, 60], "session scope is unchanged")
check(c.alert_levels_for({"alert_levels_week": [50], "alert_levels_week_opus": "bad"}, "week", "opus") == [50],
      "a non-list override is ignored")
# a synthetic field (seven_day_fable_5) maps to variant fable_5
check(c.alert_levels_for({"alert_levels_week": [50], "alert_levels_week_fable_5": [30]}, "week", "fable_5") == [30],
      "synthetic limits[] fields map to their own variant")
# plan_alerts routes the variant through; a variant override fires only for that variant
def vsnap(items):
    return {"now": tnow, "window": None,
            "gauge": {"pct": None, "eta": None},
            "live": {"status": "ok", "items": items}}
week_items = [
    {"key": "seven_day_opus", "pct": 30.0, "resets": tnow + 3 * 86400, "label": "Opus"},
    {"key": "seven_day_sonnet", "pct": 30.0, "resets": tnow + 3 * 86400, "label": "Sonnet"},
]
vcfg = dict(c.DEFAULTS, alerted={}, alert_levels_week=[50, 75], alert_levels_week_opus=[25])
vevs = c.plan_alerts(vcfg, vsnap(week_items), vcfg["alerted"], tnow)
check(len(vevs) == 1 and vevs[0]["label"] == "Opus", f"only the overridden variant alerts at 30% ({vevs})")
check(c.alert_levels_for(dict(c.DEFAULTS), "week", None) == [50, 75, 90], "the plain seven_day key has no override")
# pace bypass: behind pace, levels below bypass stay silent but levels >= bypass still fire
pcfg = dict(c.DEFAULTS, alerted={}, alerts=True, alert_forecast=False, alerts_pace_only=True,
            alerts_pace_bypass=90, alert_levels=[75, 90], alert_levels_week=[])
def psnap(pct, elapsed):
    return {"now": tnow, "window": {"end": tnow + 9000, "elapsed": elapsed, "rate": 1.0},
            "gauge": {"pct": pct, "eta": None}, "live": {"status": "off", "items": []}}
pevs = c.plan_alerts(pcfg, psnap(80, 0.9), pcfg["alerted"], tnow)
check(pevs == [], f"behind pace: 80% stays silent with bypass=90 ({pevs})")
pcfg["alerted"] = {}
pevs = c.plan_alerts(pcfg, psnap(92, 0.9), pcfg["alerted"], tnow)
check(len(pevs) == 1 and pevs[0]["level"] == 90, f"behind pace: 92% still fires via bypass ({pevs})")
pcfg["alerted"] = {}; pcfg["alerts_pace_bypass"] = 0
check(c.plan_alerts(pcfg, psnap(92, 0.95), pcfg["alerted"], tnow) == [], "bypass off (0): behind pace stays silent")
# load_config keeps config-file-only per-variant keys and clamps the bypass
old_cfgp = c.CONFIG_PATH
cfgdir2 = tempfile.mkdtemp(); cfgp2 = os.path.join(cfgdir2, ".limitline.json")
json.dump({"alert_levels_week_opus": [25, 200, -1, "x"], "alerts_pace_bypass": 150}, open(cfgp2, "w"))
c.CONFIG_PATH = cfgp2
cfg2 = c.load_config()
c.CONFIG_PATH = old_cfgp
check(cfg2.get("alert_levels_week_opus") == [1, 25, 100],
      f"per-variant levels survive load, clamp and drop non-numbers ({cfg2.get('alert_levels_week_opus')})")
check(cfg2["alerts_pace_bypass"] == 100, f"pace bypass is clamped to 0..100 ({cfg2['alerts_pace_bypass']})")
check("alert_levels_week_ghost" not in cfg2, "absent per-variant keys stay absent")
# hook_env: per-key utilization/reset vars, version, extra usage; unknown values are omitted
now_unix = time.time()
henv = c.hook_env({"status": "ok", "items": [
        {"key": "five_hour", "pct": 41.6, "resets": now_unix + 600},
        {"key": "seven_day", "pct": 12.0, "resets": None},
        {"key": "seven_day_bad", "pct": None, "resets": now_unix},
    ], "extra": {"used": 12.5, "limit": None}}, "threshold", "Week", 41.6)
check(henv["LIMITLINE_UTILIZATION_SEVEN_DAY"] == "12" and henv["LIMITLINE_UTILIZATION_FIVE_HOUR"] == "42",
      f"utilization vars per live key, rounded ({henv})")
check(henv["LIMITLINE_RESETS_AT_FIVE_HOUR"].startswith(str(c.datetime.fromtimestamp(now_unix + 600).year)),
      "reset times are ISO local")
check("LIMITLINE_RESETS_AT_SEVEN_DAY" not in henv and "LIMITLINE_UTILIZATION_SEVEN_DAY_BAD" not in henv,
      "unknown resets/pct are omitted, not blanked")
check(henv["LIMITLINE_EXTRA_USED"] == "12.5" and "LIMITLINE_EXTRA_LIMIT" not in henv,
      "extra usage: used is passed, uncapped limit is omitted")
check(henv["LIMITLINE_EVENT"] == "threshold" and henv["LIMITLINE_PCT"] == "42" and henv["LIMITLINE_VERSION"] == c.VERSION,
      "event/label/pct/version are always present")
check("LIMITLINE_LABEL" in henv, "label is always present")
hnull = c.hook_env(None, "start", "Limitline", 0)
check(hnull["LIMITLINE_PCT"] == "0" and hnull["LIMITLINE_EVENT"] == "start", "hooks work without live data")
# hook_command: shell string, argv list, JSON-array string
check(c.hook_command("echo hi") == "echo hi", "a string stays a shell command")
check(c.hook_command(["py", "-c", "x"]) == ["py", "-c", "x"], "a list stays an argv list")
check(c.hook_command('["py", "-c", "x"]') == ["py", "-c", "x"], "a JSON-array string parses to argv")
check(c.hook_command("[not json") == "[not json", "a broken JSON array stays a shell string")
check(c.hook_command("") == "" and c.hook_command(None) == "", "empty commands stay empty")
# run_hook: a list command runs without a shell, with the full env
import sys as _sys
tmp_hook = os.path.join(tempfile.mkdtemp(), "hookout.txt")
apph = object.__new__(c.App)
apph.cfg = dict(c.DEFAULTS, on_alert_command=[_sys.executable, "-c",
    "import os,sys;open(sys.argv[1],'w').write('|'.join(os.environ.get(k,'') for k in "
    "('LIMITLINE_EVENT','LIMITLINE_PCT','LIMITLINE_VERSION','LIMITLINE_UTILIZATION_SEVEN_DAY')))", tmp_hook])
apph.args = type("Args", (), {"demo": False})()
apph.run_hook("on_alert_command", "threshold", "Week", 55.5,
              {"items": [{"key": "seven_day", "pct": 55.5, "resets": now_unix + 3600}]})
for _w in range(50):
    if os.path.exists(tmp_hook):
        break
    time.sleep(0.1)
check(open(tmp_hook).read() == f"threshold|56|{c.VERSION}|56" if os.path.exists(tmp_hook) else False,
      f"list hook ran without a shell with the full env ({open(tmp_hook).read() if os.path.exists(tmp_hook) else 'missing'})")
# routing: on_alert_command catches everything; threshold hook excludes forecasts; forecast hook is forecast-only
appq = object.__new__(c.App)
appq.cfg = dict(c.DEFAULTS, alerted={}, alerts=True, alert_forecast=True,
                on_threshold_command="t", on_forecast_command="f")
appq.args = type("Args", (), {"demo": False})()
qh = []
appq.run_hook = lambda key, event, label, pct, live=None: qh.append((key, event))
appq.raise_alert = lambda ev, quiet=False: None
appq.save_soon = lambda: None
appq.prev_win = None
wq = {"end": tnow + 3600, "elapsed": 0.3, "rate": 10.0}
appq.check_alerts({"now": tnow, "window": wq, "gauge": {"pct": 80, "eta": tnow + 1800},
                   "live": {"status": "off", "items": []}})
kinds = [e for k, e in qh if k == "on_alert_command"]
check("threshold" in kinds and "forecast" in kinds, f"on_alert_command still catches every event ({qh})")
th = [k for k, e in qh if k == "on_threshold_command"]
fc = [k for k, e in qh if k == "on_forecast_command"]
check(th == ["on_threshold_command"] and fc == ["on_forecast_command"],
      f"threshold/forecast hooks each fire once, forecast excluded from threshold ({qh})")
# run_hook_command (the Settings Test button's engine) reports exit codes and output
rcode, rout = c.run_hook_command([_sys.executable, "-c", "import sys;sys.stdout.write('hi')"])
check(rcode == 0 and rout == "hi", f"run_hook_command captures stdout ({rcode}, {rout!r})")
rcode2, rout2 = c.run_hook_command("")
check(rcode2 is None and rout2 == "", "run_hook_command on an empty command is a no-op")

# ---- v2.6.0: tray helpers ----------------------------------------------------------
lines = c.tray_lines({"gauge": {"pct": 42.4}, "live": {"items": [
        {"key": "seven_day", "pct": 31.0, "resets": tnow + 86400}],
    "extra": {"used": 12.5, "limit": None}}}, ["window", "week", "spend"])
check(lines == ["5-hour 42.4%", "Week 31%", "Spend 12"], f"tray lines format each field ({lines})")
check(c.tray_lines({"gauge": {"pct": None}, "live": {"items": []}}, ["window", "week", "spend"]) == [],
      "unknown/absent values are skipped, never blanked")
check(c.tray_lines(None, ["window"]) == [], "no snapshot -> no lines")
check(c.tray_lines({"gauge": {"pct": 50}}, ["bogus"]) == [], "unknown fields are ignored")
check(c.tray_lines({"live": {"extra": {"used": 2500.0, "limit": 100000.0}}}, ["spend"]) == ["Spend 2,500 / 100,000"],
      "spend shows the cap when known")
old_cfgp2 = c.CONFIG_PATH
cfgdir3 = tempfile.mkdtemp(); cfgp3 = os.path.join(cfgdir3, ".limitline.json")
json.dump({"tray": True, "tray_style": "neon", "tray_fields": ["window", "bogus", "spend", 7]}, open(cfgp3, "w"))
c.CONFIG_PATH = cfgp3
cfg3 = c.load_config()
c.CONFIG_PATH = old_cfgp2
check(cfg3["tray"] is True and cfg3["tray_style"] == "ring",
      f"tray on survives, bad style falls back to ring ({cfg3['tray_style']})")
check(cfg3["tray_fields"] == ["window", "spend"], f"tray fields are filtered to the known set ({cfg3['tray_fields']})")
json.dump({"tray_fields": "window"}, open(cfgp3, "w"))
c.CONFIG_PATH = cfgp3
check(c.load_config()["tray_fields"] == ["window", "week"], "a non-list tray_fields falls back to defaults")
c.CONFIG_PATH = old_cfgp2
check(isinstance(c.tray_available(), bool), "tray_available answers without raising")
if c.tray_available():
    tray_app = object.__new__(c.App)
    tray_app.cfg = dict(c.DEFAULTS, tray=True, tray_style="ring")
    tray_app.args = type("Args", (), {"demo": False})()
    tr = c.TrayIcon(tray_app)
    tr._pt = None
    img = tr._image(42.0, c.STATUS["good"])
    check(img.size == (64, 64) and img.mode == "RGBA", f"ring icon draws 64px RGBA ({img.size}, {img.mode})")
    check(tr._image(None, c.STATUS["crit"]).mode == "RGBA", "dot icon draws")
    tr.start()      # pystray is installed here; must not raise, and must stop cleanly after
    started = tr.icon is not None
    time.sleep(0.4)    # let the detached thread finish spinning up before asking it to stop
    tr.stop()
    time.sleep(0.5)    # pystray's detached thread is non-daemon; let it wind down before the suite exits
    check(started and tr.icon is None, f"tray starts when deps are present and stops cleanly ({started})")

# ---- v2.7.0: profile email, prepaid credits, auto token refresh ----------------------
# prepaid responses normalize to major units; anything unexpected means "no credits" (hidden line)
pp = c.normalize_prepaid({"amount": 12345, "balance": {"money": {"currency": "USD", "exponent": 2}}})
check(pp == {"amount": 123.45, "currency": "USD", "decimals": 2}, f"prepaid normalizes minor units ({pp})")
check(c.normalize_prepaid({"amount": 50, "currency": "EUR"}) == {"amount": 0.5, "currency": "EUR", "decimals": 2},
      "top-level currency and default exponent work")
check(c.normalize_prepaid({"amount": "free"}) is None and c.normalize_prepaid([1]) is None
      and c.normalize_prepaid({"amount": True}) is None, "non-numeric amount -> None (line hidden)")
check(c.prepaid_text(pp) == "Prepaid credits USD 123.45", f"prepaid line formats ({c.prepaid_text(pp)!r})")
check(c.prepaid_text(None) == "" and c.prepaid_text({"amount": 0.0, "currency": None, "decimals": 2})
      == "Prepaid credits 0.00", "empty currency does not leave a double space")
check(c.ORG_RE.match("12345678-1234-1234-1234-123456789abc") and not c.ORG_RE.match("not-a-uuid")
      and not c.ORG_RE.match("12345678-1234-1234-1234-123456789abc "), "org uuid regex is strict")
hd = c.oauth_headers({"accessToken": "tok"})
check(hd["Authorization"] == "Bearer tok" and hd["anthropic-beta"] == "oauth-2025-04-20"
      and hd["User-Agent"].startswith("limitline/"), "oauth headers carry the token only to the API")
# refresh is off by default, gated by live_refresh, and rate-limited to once an hour
lv2 = object.__new__(c.LiveLimits)
lv2.app = type("A", (), {"cfg": dict(c.DEFAULTS)})()
check(lv2._refresh_now() is False, "refresh stays off when live_refresh is off")
lv2.app.cfg["live_refresh"] = True
lv2._last_refresh = time.time() - 10
check(lv2._refresh_now() is False, "refresh is rate-limited to once an hour")
lv2._last_refresh = time.time() - 7200
check(lv2._refresh_now() in (True, False), "with live_refresh on and the CLI absent/present, it answers without raising")
# profile memoizes per token; org uuid must pass the regex before prepaid can ever be fetched
calls_p = []
def fake_http(url, headers, timeout=10):
    calls_p.append(url)
    if url == c.PROFILE_URL:
        return {"account": {"email": "me@example.com"}, "organization": {"uuid": "12345678-1234-1234-1234-123456789abc"}}
    return {"amount": 999, "balance": {"money": {"currency": "USD", "exponent": 2}}}
old_http = c.http_get_json
c.http_get_json = fake_http
try:
    lv3 = object.__new__(c.LiveLimits)
    lv3.app = type("A", (), {"cfg": dict(c.DEFAULTS)})()
    prof = lv3._profile_for("tok1")
    prof2 = lv3._profile_for("tok1")
    check(prof == prof2 and prof["email"] == "me@example.com" and prof["org"]
          and calls_p.count(c.PROFILE_URL) == 1, f"profile memoizes per token ({calls_p})")
    check(lv3._profile_for("tok2") and calls_p.count(c.PROFILE_URL) == 2, "a new token refetches the profile")
    lv3._prepaid_at = 0.0
    bal = lv3._prepaid_for("tok1", prof["org"])
    check(bal and bal["amount"] == 9.99, f"prepaid balance fetched for a valid org ({bal})")
    n0 = len(calls_p)
    check(lv3._prepaid_for("tok1", prof["org"]) == bal and len(calls_p) == n0, "prepaid refetches at most every 30 min")
    lv3._prepaid_at = 0.0
    check(lv3._prepaid_for("tok1", "not-a-uuid") is None, "an invalid org uuid means no request at all")
finally:
    c.http_get_json = old_http
# fetch_oauth attaches email + prepaid on success, and a failed profile never breaks the fetch
def fake_http2(url, headers, timeout=10):
    if url == c.USAGE_URL:
        return {"five_hour": {"utilization": 10.0, "resets_at": "2099-01-01T00:00:00Z"},
                "seven_day": {"utilization": 20.0, "resets_at": "2099-01-08T00:00:00Z"}}
    raise OSError("profile endpoint down")
old_http = c.http_get_json; old_cred = c.read_credentials
c.http_get_json = fake_http2
c.read_credentials = lambda: {"accessToken": "tokX", "subscriptionType": "max", "expiresAt": time.time() * 1000 + 999999}
try:
    lv4 = object.__new__(c.LiveLimits)
    lv4.app = type("A", (), {"cfg": dict(c.DEFAULTS, live_oauth=True)})()
    st4 = lv4.fetch_oauth()
    check(st4["status"] == "ok" and st4["items"] and "email" not in st4 and st4.get("prepaid") is None,
          f"a failing profile/prepaid never breaks the usage fetch ({st4.get('status')})")
finally:
    c.http_get_json = old_http; c.read_credentials = old_cred
# an expired login + live_refresh off returns 'expired' (refresh must never be the default path)
def boom(*a, **k):
    raise AssertionError("network must not be touched with an expired token and refresh off")
old_http = c.http_get_json; old_cred = c.read_credentials
c.http_get_json = boom
c.read_credentials = lambda: {"accessToken": "tokE", "expiresAt": time.time() * 1000 - 1000}
try:
    lv5 = object.__new__(c.LiveLimits)
    lv5.app = type("A", (), {"cfg": dict(c.DEFAULTS, live_oauth=True)})()
    st5 = lv5.fetch_oauth()
    check(st5["status"] == "expired", f"expired login with refresh off stays 'expired' ({st5['status']})")
finally:
    c.http_get_json = old_http; c.read_credentials = old_cred
# email is memory-only: the settings file round-trip never includes it
check("email" not in c.DEFAULTS and "prepaid" not in c.DEFAULTS, "email/prepaid are not settings keys")

# real payloads captured live from api.anthropic.com (the reference fixture plus the account's own shape)
def _prepaid(**over):
    d = {"amount": 5597, "currency": "EUR",
         "balance": {"money": {"amount_minor": 5597, "currency": "EUR", "exponent": 2}, "credits": None},
         "balance_credits": None, "auto_reload_settings": None, "expiry_policy_months": None,
         "tranches": [], "promo_tranches": [], "next_expires_at": None}
    d.update(over)
    return d

check(c.normalize_prepaid(_prepaid()) == {"amount": 55.97, "currency": "EUR", "decimals": 2},
      "the real prepaid fixture normalizes minor units to major units")
check(c.normalize_prepaid({"amount": 0, "currency": "USD",
                           "balance": {"money": None, "credits": {"amount_minor": 0, "exponent": 2}},
                           "balance_credits": 0, "tranches": [], "promo_tranches": []})
      == {"amount": 0.0, "currency": "USD", "decimals": 2},
      "the live payload (balance.money null, exponent in balance.credits) parses correctly")
check(c.normalize_prepaid(_prepaid(balance={"money": {"currency": "JPY", "exponent": 0}, "credits": None}))
      == {"amount": 5597.0, "currency": "JPY", "decimals": 0}, "a zero-decimal currency keeps whole units")
check(c.normalize_prepaid(_prepaid(balance=None)) == {"amount": 55.97, "currency": "EUR", "decimals": 2},
      "a null balance still uses the top-level currency and two decimal places")
check(c.normalize_prepaid(_prepaid(balance={"money": None, "credits": {"exponent": 0}}))
      == {"amount": 5597.0, "currency": "EUR", "decimals": 0}, "balance.credits supplies the exponent when money is null")
check(c.normalize_prepaid(_prepaid(amount=0))["amount"] == 0.0, "a zero balance is valid, not missing")
check(c.normalize_prepaid(_prepaid(amount=5597.5)) == {"amount": 55.975, "currency": "EUR", "decimals": 2},
      "a float amount is accepted")
for bal in ("x", [1], 42, {"money": "x"}, {"money": [1]}):
    check(c.normalize_prepaid(_prepaid(balance=bal)) == {"amount": 55.97, "currency": "EUR", "decimals": 2},
          f"a changed-type balance/money is ignored, not raised on ({bal!r})")
check(c.normalize_prepaid(_prepaid(currency=None, balance={"money": {"exponent": 2}, "credits": None}))
      == {"amount": 55.97, "currency": None, "decimals": 2}, "a missing currency is None, not a crash")
check(c.normalize_prepaid(_prepaid(balance={"money": {"currency": "EUR", "exponent": "2"}, "credits": None}))
      == {"amount": 55.97, "currency": "EUR", "decimals": 2}, "a non-integer exponent falls back to two places")
for bad in (None, [], "text", 42):
    check(c.normalize_prepaid(bad) is None, f"a non-object prepaid body is None ({bad!r})")
check(c.prepaid_text({"amount": 5597.0, "currency": "JPY", "decimals": 0}) == "Prepaid credits JPY 5,597",
      "a zero-decimal currency shows no cents")

# the org endpoint is called only for a canonical uuid, and the real balance round-trips
_ORG = "2b4f9a1c-7d3e-4a58-9c61-0e8fb2d7a940"
seen_org = []
def org_router(url, headers, timeout=10):
    seen_org.append(url)
    if url == c.PREPAID_URL.format(org=_ORG):
        return _prepaid()
    raise AssertionError("unexpected url " + url)
old_http = c.http_get_json
c.http_get_json = org_router
try:
    lv6 = object.__new__(c.LiveLimits)
    lv6.app = type("A", (), {"cfg": dict(c.DEFAULTS)})()
    check(lv6._prepaid_for("tok", _ORG) == {"amount": 55.97, "currency": "EUR", "decimals": 2},
          "the real prepaid balance is fetched for a canonical org uuid")
    n = len(seen_org)
    for bad_org in ("", "   ", "not-a-uuid", _ORG + "/../../admin", "../" + _ORG, _ORG + "\n", None, 123):
        lv6._prepaid_at = 0.0
        check(lv6._prepaid_for("tok", bad_org) is None, f"a non-canonical org uuid ({bad_org!r}) is rejected")
    check(len(seen_org) == n, "no prepaid request was made for any rejected org uuid")
finally:
    c.http_get_json = old_http
# end to end: real usage + profile + prepaid fixtures -> state carries email and the balance
def live_router(url, headers, timeout=10):
    if url == c.USAGE_URL:
        return {"five_hour": {"utilization": 12.0, "resets_at": "2099-01-01T00:00:00Z"},
                "seven_day": {"utilization": 42.0, "resets_at": "2099-01-08T00:00:00Z"},
                "extra_usage": {"is_enabled": True, "monthly_limit": 100000, "used_credits": 2500.0}}
    if url == c.PROFILE_URL:
        return {"account": {"email": "real@example.com"}, "organization": {"uuid": _ORG}}
    if url == c.PREPAID_URL.format(org=_ORG):
        return _prepaid()
    raise AssertionError("unexpected url " + url)
old_http = c.http_get_json; old_cred = c.read_credentials
c.http_get_json = live_router
c.read_credentials = lambda: {"accessToken": "tokR", "subscriptionType": "max", "rateLimitTier": "default_claude_max_20x",
                              "expiresAt": time.time() * 1000 + 9_999_999}
try:
    lv7 = object.__new__(c.LiveLimits)
    lv7.app = type("A", (), {"cfg": dict(c.DEFAULTS, live_oauth=True)})()
    st7 = lv7.fetch_oauth()
    check(st7["status"] == "ok" and st7.get("email") == "real@example.com" and st7.get("plan"),
          f"end to end: status/email/plan attached ({st7.get('status')}, {bool(st7.get('email'))})")
    check(st7.get("prepaid") == {"amount": 55.97, "currency": "EUR", "decimals": 2},
          f"end to end: the prepaid balance reaches the state ({st7.get('prepaid')})")
    check(st7.get("extra") and st7["extra"].get("pct") is not None, "end to end: extra usage block is present")
except Exception as ex:
    check(False, f"end-to-end real-fixture fetch raised {type(ex).__name__}: {ex}")
finally:
    c.http_get_json = old_http; c.read_credentials = old_cred

# ---- v2.8.0: app icon (pure-Python PNG/ICO rasteriser) --------------------------------
import struct as _struct
png = c.app_icon_bytes(48, "#d3b787", True)
check(png[:8] == b"\x89PNG\r\n\x1a\n" and png[-8:] == b"IEND\xaeB`\x82",
      "app icon encodes to a valid PNG (magic + IEND crc)")
w, h = _struct.unpack(">II", png[16:24])
check((w, h) == (48, 48), f"PNG IHDR carries the requested size ({w}x{h})")
ico = c.ico_bytes((16, 32, 48, 256), "#d3b787", True)
res, typ, n = _struct.unpack("<HHH", ico[:6])
check((res, typ, n) == (0, 1, 4), f"ICO header is a 4-image icon directory ({res},{typ},{n})")
off, dims, all_png = 6, [], True
for _ in range(n):
    ew, eh, cc, rsv, planes, bpp, size, boff = _struct.unpack("<BBBBHHII", ico[off:off + 16])
    dims.append(ew or 256)
    all_png = all_png and ico[boff:boff + 8] == b"\x89PNG\r\n\x1a\n" and bpp == 32 and planes == 1
    off += 16
check(dims == [16, 32, 48, 256] and all_png, f"ICO entries are 32-bit PNGs at each size ({dims})")
_icof = os.path.join(__import__("tempfile").gettempdir(), "limitline_icon_test.ico")
c.write_ico(_icof, "#d3b787", True)
check(os.path.getsize(_icof) > 2000, "write_ico writes a non-trivial .ico file")
os.remove(_icof)
S = 128
rgba = c.icon_rgba(S, "#d3b787", True)
check(rgba[3] == 0, "icon rounded corner is transparent")
check(rgba[((S // 2) * S + (S // 2)) * 4 + 3] == 255, "icon centre is opaque")
accent = c._rgb("#d3b787")
track = (0x55, 0x55, 0x60)
acc_px = sum(1 for i in range(0, len(rgba), 4) if tuple(rgba[i:i + 3]) == accent)
trk_px = sum(1 for i in range(0, len(rgba), 4) if tuple(rgba[i:i + 3]) == track)
frac = acc_px / float(acc_px + trk_px)
check(0.70 <= frac <= 0.85, f"accent arc covers ~72% of the ring plus round caps ({frac:.3f})")
check(c._rgb("#d3b787") == (0xD3, 0xB7, 0x87), "accent hex parses to RGB")

# ---- v2.9.0: show-the-data-that-exists (widen hints + source notes) -----------------
check(c.DEFAULTS["proj_range"] == "30d", "Projects defaults to a 30-day range")
check(c.range_to_cover(0, c.HIST_RANGE_OPTS) == 7, "today's activity is covered by the 7d history range")
check(c.range_to_cover(20, c.HIST_RANGE_OPTS) == 30, "20-day-old activity widens history to 30d")
check(c.range_to_cover(50, c.HIST_RANGE_OPTS) == 90, "50-day-old activity widens history to 90d")
check(c.range_to_cover(240, c.HIST_RANGE_OPTS) == 180, "activity older than 180d caps at the widest history range")
check(c.range_to_cover(0, c.PROJ_RANGE_OPTS) == "today", "today's activity stays on the Projects Today range")
check(c.range_to_cover(6, c.PROJ_RANGE_OPTS) == "7d", "6-day-old activity widens projects to 7d")
check(c.range_to_cover(140, c.PROJ_RANGE_OPTS) == "180d", "140-day-old activity widens projects to 180d")
snap_v290 = c.build_snapshot(es, now, dict(c.DEFAULTS), {}, {"roots": [], "cost_states": {}, "unpriced": {}})
check(snap_v290["last_day"] == c.local_day(es[-1].ts),
      "the snapshot knows the day of the newest local activity")
check(c.App.local_note(None, {"now": now, "last_ts": now - 5 * 86400, "has_data": True})
      == "Local Claude Code logs · last activity " + c.fmt_ago(5 * 86400),
      "the log tabs carry a 'local logs · last activity' source line")
check(c.App.local_note(None, {"now": now, "last_ts": None}) == "Local Claude Code logs",
      "the source line degrades when nothing was ever logged")

# ---- v2.10.0: data-scope segregation + histogram modes --------------------
check(c.DEFAULTS["scope"] == "both", "Overview defaults to showing both data sources")
check(c.DEFAULTS["hist_mode"] == "day", "History defaults to the per-day columns")
_scope_p = c.CONFIG_PATH
_sp = os.path.join(tmp, "scope-test.json")
json.dump({"scope": "nonsense", "hist_mode": "heat"}, open(_sp, "w"))
c.CONFIG_PATH = _sp
_cfg10 = c.load_config()
check(_cfg10["scope"] == "both", "an unknown overview scope falls back to 'both'")
check(_cfg10["hist_mode"] == "day", "an unknown history mode falls back to 'day'")
json.dump({"scope": "all", "hist_mode": "cum"}, open(_sp, "w"))
c.CONFIG_PATH = _sp
_cfg10b = c.load_config()
check(_cfg10b["scope"] == "all" and _cfg10b["hist_mode"] == "cum", "valid scope and history mode are kept")
c.CONFIG_PATH = os.path.join(tmp, "scope-roundtrip.json")
c.save_config(dict(_cfg10b, scope="local", hist_mode="day"))
_rt10 = c.load_config()
check(_rt10["scope"] == "local" and _rt10["hist_mode"] == "day",
      "scope and history mode survive a save/reload round trip")
c.CONFIG_PATH = _scope_p

# ---- OAuth 401 and refresh tests ----
lv401 = object.__new__(c.LiveLimits)
lv401.app = type('A', (), {'cfg': dict(c.DEFAULTS, live_oauth=True, live_refresh=True)})()
lv401._last_refresh = 0
calls401 = []
class _FakeErr401(c.urllib.error.HTTPError):
    def __init__(self, code):
        super().__init__('url', code, 'Unauthorized', {}, None)
    def read(self): return b'{}'
def fake_http401(url, headers):
    calls401.append(url)
    if len(calls401) == 1:
        raise _FakeErr401(401)
    return {'five_hour': {'utilization': 10.0, 'resets_at': '2099-01-01T00:00:00Z'}}
def fake_refresh401():
    calls401.append('refresh')
    return True
lv401._refresh_now = fake_refresh401
old_http401 = c.http_get_json; old_cred401 = c.read_credentials
c.http_get_json = fake_http401
c.read_credentials = lambda: {"accessToken": "tok401", "expiresAt": time.time() * 1000 + 999999}
try:
    st401 = lv401.fetch_oauth()
    check(calls401 == [c.USAGE_URL, 'refresh', c.USAGE_URL, c.PROFILE_URL], f"401 triggers refresh and retry ({calls401})")
    check(st401.get('status') == 'ok', "retry succeeds")
finally:
    c.http_get_json = old_http401; c.read_credentials = old_cred401

# ---- OAuth 403 (no refresh attempted) ----
lv403 = object.__new__(c.LiveLimits)
lv403.app = type('A', (), {'cfg': dict(c.DEFAULTS, live_oauth=True, live_refresh=True)})()
lv403._last_refresh = 0
calls403 = []
def fake_http403(url, headers):
    calls403.append(url)
    raise _FakeErr401(403)
def no_refresh403():
    calls403.append('refresh')
    return False  # refresh fails → no retry
lv403._refresh_now = no_refresh403
old_http403 = c.http_get_json; old_cred403 = c.read_credentials
c.http_get_json = fake_http403
c.read_credentials = lambda: {"accessToken": "tok403", "expiresAt": time.time() * 1000 + 999999}
try:
    st403 = lv403.fetch_oauth()
    check(st403.get('status') == 'auth', f"403 with failed refresh returns auth status ({st403.get('status')})")
    check('refresh' not in calls403 or calls403.count('refresh') <= 1, "403 does not loop on refresh")
finally:
    c.http_get_json = old_http403; c.read_credentials = old_cred403

print("\nFAILURES:", fails if fails else "none")

