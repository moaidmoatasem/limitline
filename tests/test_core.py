import json, os, sys, time, tempfile, glob, math
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import limitline as c

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
check(c.plan_label("max", "default_claude_max_20x") == "Max 20x", "plan label")

# snapshot: local mode
cfg = c.load_config(reset=True)
demo = c.DemoStore()
es = demo.entries(now - 31 * 86400)
t0 = time.time()
snap = c.build_snapshot(es, time.time(), cfg, {"status": "off"}, {"roots": [], "files": 0, "entries": len(es), "demo": True})
dt = time.time() - t0
check(snap["window"] is not None and snap["window"]["src"] == "local", "demo has active local window")
check(snap["gauge"]["pct"] is not None and snap["limit_src"] == "auto", f"gauge vs auto record: {snap['gauge']['pct']:.1f}% (record {snap['record']:.2f})")
check(abs(sum(b["agg"][4] for b in snap["daily"]) - snap["kpi"]["30d"]["agg"][4]) < 1e-6, "daily sums == 30d total")
check(abs(sum(sum(r) for r in snap["heat"]) - snap["kpi"]["30d"]["agg"][4]) < 1e-6, "heatmap sums == 30d total")
check(abs(sum(p["val"] for p in snap["projects"]["7d"]) - snap["kpi"]["7d"]["agg"][4]) < 1e-6, "projects 7d == 7d total")
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

# formatting
check(c.fmt_tokens(1234) == "1.2k" and c.fmt_tokens(1840000) == "1.84M" and c.fmt_tokens(312000) == "312k", "fmt_tokens")
check(c.parse_amount("5M") == 5e6 and c.parse_amount("$12.5") == 12.5 and c.parse_amount("250k") == 250000, "parse_amount")
check(c.nice_scale(7.3) == (2.5, 7.5), f"nice_scale {c.nice_scale(7.3)}")

# real Claude Code log in this workspace vs Claude Code's own cost record
real = os.path.expanduser("~/.claude/projects")
rs = c.LogStore()
rs.scan([real], 0)
res = rs.entries(0)
cost_states = []
for p in glob.glob(real + "/**/*.jsonl", recursive=True):
    for ln in open(p):
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        if d.get("type") == "cost-state":
            cost_states.append(d)
if cost_states:
    cs = cost_states[-1]
    mine = sum(e.cost for e in res)
    print(f"   real log: {len(res)} messages, my cost ${mine:.4f} vs Claude Code totalCostUSD ${cs['totalCostUSD']:.4f}")
    mu = list(cs["modelUsage"].values())[0]
    mine_out = sum(e.out for e in res); mine_cr = sum(e.cr for e in res)
    print(f"   tokens  out {mine_out} vs {mu['outputTokens']} · cache read {mine_cr} vs {mu['cacheReadInputTokens']}")

# ---- audit regressions -------------------------------------------------------
import threading, http.server
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
except urllib.error.HTTPError as ex:
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
print("\nFAILURES:", fails if fails else "none")

# ---- official status-line bridge ----------------------------------------------
import subprocess
td = tempfile.mkdtemp()
cfgdir = os.path.join(td, "acct"); os.makedirs(cfgdir)
env = dict(os.environ, CLAUDE_CONFIG_DIR=cfgdir, HOME=td)
script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "limitline.py")
payload = {"session_id": "x", "transcript_path": "/secret/path", "cwd": "/secret",
           "rate_limits": {"five_hour": {"used_percentage": 23.5, "resets_at": now + 3600},
                           "seven_day": {"used_percentage": 41.2, "resets_at": now + 86400},
                           "spend_limit": {"used_percentage": 1, "resets_at": now + 5}}}
r = subprocess.run([sys.executable, script, "--statusline", "--config-dir", cfgdir], input=json.dumps(payload),
                   capture_output=True, text=True, env=env, timeout=20)
check(r.stdout == "5h 24% \u00b7 7d 41%" or r.stdout.startswith("5h 2"), f"statusline prints a short line ({r.stdout!r})")
c.CONFIG_PATH = os.path.join(cfgdir, ".limitline.json")
b = c.read_bridge()
check(b and [i["key"] for i in b[0]] == ["five_hour", "seven_day"] and abs(b[0][0]["pct"] - 23.5) < 1e-9, "bridge file read back")
saved = open(c.live_file_path()).read()
check("secret" not in saved and "transcript" not in saved, "bridge file stores only rate_limits, nothing else from the payload")
check(c.read_bridge(now + 7200)[0][0]["key"] == "seven_day", "expired window is dropped")
r = subprocess.run([sys.executable, script, "--statusline", "--config-dir", cfgdir, "--then", "echo CHAINED"], input=json.dumps(payload),
                   capture_output=True, text=True, env=env, timeout=20)
check(r.stdout.strip() == "CHAINED", f"chained status line still runs ({r.stdout!r})")
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
print("\nFAILURES:", fails if fails else "none")
