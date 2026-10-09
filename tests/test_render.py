"""Render-path checks for the chart widgets (needs a display; skips cleanly without one).

Run: python tests/test_render.py ; must end with `FAILURES: none`.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

try:
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
except Exception as ex:  # noqa: BLE001 - headless CI has no display
    print("SKIP: no display (%s)" % ex)
    print("FAILURES: none")
    sys.exit(0)

import limitline as c

cfg = dict(c.DEFAULTS)
S = c.detect_scale(root)
app = type("Stub", (), {})()
app.th = c.make_theme(cfg["theme"], cfg["accent"])
app.f = c.make_fonts(root)
app.S = S
app.px = lambda n: int(round(n * S))
app.CW = app.px(392) - app.px(48) - 2
app.root = root
app.img = lambda *a, **k: c.App.img(app, *a, **k)
app.tip = type("Tip", (), {"show": lambda self, *a: None, "hide": lambda self, *a: None})()
parent = tk.Frame(root)
parent.pack()
SERIES = set(app.th["series"].values())

def bars(canvas):
    return [it for it in canvas.find_all()
            if canvas.type(it) in ("rectangle", "polygon") and canvas.itemcget(it, "fill") in SERIES]

# synthetic buckets: 10 days, usage on days 2 and 7
buckets = []
for i in range(10):
    v = {2: 8.0, 7: 24.0}.get(i, 0.0)
    buckets.append({"day": 100 + i, "fam": ({"opus": v} if v else {}),
                    "agg": [v * 1000, v * 100, 0, 0, v, 5 if v else 0]})
bc = c.BarChart(app, parent, app.CW, app.px(112), buckets, "cost",
                lambda i, b: str(i), lambda i: "", mark_last=True)
root.update()
totals = [sum(b["fam"].values()) for b in buckets]
step, top = c.nice_scale(max(totals))
ph = bc.y1 - bc.y0
covered = set()
for it in bars(bc.c):
    x0, y0, x1, y1 = bc.c.bbox(it)
    covered.add(int(((x0 + x1) / 2.0 - bc.x0) // bc.slot))
check(covered == {2, 7}, f"bars cover exactly the nonzero buckets ({sorted(covered)})")
ok = True
for i, t in enumerate(totals):
    if t <= 0:
        continue
    tops, bots = [], []
    for it in bars(bc.c):
        x0, y0, x1, y1 = bc.c.bbox(it)
        if bc.x0 + i * bc.slot <= (x0 + x1) / 2.0 < bc.x0 + (i + 1) * bc.slot:
            tops.append(y0); bots.append(y1)
    if not tops or abs(min(tops) - (bc.y1 - t / top * ph)) > 2.0 or abs(max(bots) - bc.y1) > 1.0:
        ok = False
check(ok, "bars sit on the baseline with proportional heights")
texts = [bc.c.itemcget(it, "text") for it in bc.c.find_all() if bc.c.type(it) == "text"]
check(c.fmt_axis(top, "cost") in texts, f"axis shows the nice max ({c.fmt_axis(top, 'cost')!r})")

# BarChart upgrades: value labels, peak marker, 7-day rolling-average trend line
bc2 = c.BarChart(app, parent, app.CW, app.px(150), buckets, "cost",
                 lambda i, b: str(i), lambda i: "", mark_last=False, peak=True,
                 values=True, avg_window=7)
root.update()
texts2 = [bc2.c.itemcget(it, "text") for it in bc2.c.find_all() if bc2.c.type(it) == "text"]
check(c.fmt_axis(8.0, "cost") in texts2 and c.fmt_axis(24.0, "cost") in texts2,
      "value labels show above used buckets")
check(texts2.count(c.fmt_axis(24.0, "cost")) == 1,
      "the busiest bucket is labelled exactly once (peak marker replaces its value label)")
ovals = [it for it in bc2.c.find_all() if bc2.c.type(it) == "oval"]
check(bool(ovals) and bc2.c.itemcget(ovals[0], "fill") == app.th["accent"],
      "peak marker dot drawn above the busiest bar")
if ovals:
    ob = bc2.c.bbox(ovals[0])
    clash = []
    for it in bc2.c.find_all():
        if bc2.c.type(it) == "text":
            tb = bc2.c.bbox(it)
            if tb and tb[0] < ob[2] and tb[2] > ob[0] and tb[1] < ob[3] and tb[3] > ob[1]:
                clash.append(bc2.c.itemcget(it, "text"))
    check(not clash, f"no label overlaps the peak dot ({clash})")
avglines = [it for it in bc2.c.find_all()
            if bc2.c.type(it) == "line" and bc2.c.itemcget(it, "dash")]
check(len(avglines) == 1, f"rolling average drawn as one dashed line ({len(avglines)})")
coords = bc2.c.coords(avglines[0])
pts = [(coords[j], coords[j + 1]) for j in range(0, len(coords), 2)]
ph2 = bc2.y1 - bc2.y0
# at the last bucket the trailing window is totals[3..9] = 24 (the 8 has rolled out)
avg_last = 24.0 / 7.0
check(abs(pts[-1][1] - (bc2.y1 - avg_last / top * ph2)) < 2.0,
      "trend line's last point sits at the trailing 7-day average")
check(len(pts) == 4 and abs(pts[0][0] - (bc2.x0 + 6.5 * bc2.slot)) < 1.5,
      f"trend line starts at the first day with a full 7-day window ({len(pts)} points)")
check(pts == sorted(pts, key=lambda p: p[0]), "trend line points run left to right")

# CumulativeChart: running totals, staircase plateaus on empty days, hover running total
cc = c.CumulativeChart(app, parent, app.CW, app.px(150), buckets, "cost",
                       lambda i, b: str(i) if i % 3 == 0 else None, lambda i: "")
root.update()
polys = [it for it in cc.c.find_all() if cc.c.type(it) == "polygon"]
check(len(polys) == 1, f"cumulative chart draws a single filled area ({len(polys)})")
check(cc.cum == [0, 0, 8.0, 8.0, 8.0, 8.0, 8.0, 32.0, 32.0, 32.0],
      f"running totals accumulate the day values ({cc.cum})")
check(cc.cum == sorted(cc.cum), "running totals never decrease")
_st, _top = c.nice_scale(cc.cum[-1])
py = cc.y1 - 8.0 / _top * (cc.y1 - cc.y0)
co = cc.c.coords(polys[0])
segs = []
for j in range(0, len(co) - 3, 2):
    if abs(co[j + 1] - co[j + 3]) < 1e-6 and abs(co[j + 1] - py) < 0.5:
        segs.append((co[j], co[j + 2]))
check(len(segs) >= 4, f"empty days read as flat steps on the staircase ({len(segs)} plateaus at 8)")
cap2, hides = {}, [0]


def _cap_show(self, text, x, y):
    cap2["text"] = text


def _cap_hide(self, *_a):
    hides[0] += 1


app.tip = type("Tip", (), {"show": _cap_show, "hide": _cap_hide})()
ev = type("E", (), {"x": cc.x0 + 8 * cc.slot + 2, "x_root": 100, "y_root": 100})()
cc.motion(ev)
check("\nrunning total" in cap2.get("text", "") and c.fmt_metric(32.0, "cost") in cap2.get("text", ""),
      "hover shows the running total on its own line")
n_hide = hides[0]
cc.leave()
check(hides[0] == n_hide + 1, "leaving the cumulative chart hides the tooltip")

# heatmap: 3 lit cells land on the right squares
heat = [[0.0] * 24 for _ in range(7)]
heat_n = [[0] * 24 for _ in range(7)]
for d, h, v in ((1, 9, 3.0), (4, 22, 9.0), (6, 0, 1.0)):
    heat[d][h] = v
    heat_n[d][h] = 2
s = {"heat": heat, "heat_n": heat_n, "heat_max": 9.0, "metric": "cost", "heat_days": 180}
hm = c.Heatmap(app, parent, app.CW, s)
root.update()
lit = [it for it in hm.c.find_all()
       if hm.c.type(it) == "rectangle" and hm.c.itemcget(it, "fill") != app.th["grid"]]
check(len(lit) == 3, f"heatmap lights exactly the 3 active cells ({len(lit)})")
ok = True
for d, h, _ in ((1, 9, 3.0), (4, 22, 9.0), (6, 0, 1.0)):
    ex, ey = hm.lw + h * hm.cw, d * hm.ch
    if not [it for it in lit
            if abs((hm.c.bbox(it)[0] + hm.c.bbox(it)[2]) / 2 - (ex + hm.cw / 2)) < 2
            and abs(hm.c.bbox(it)[1] - ey) < 2]:
        ok = False
check(ok, "heatmap lit cells sit on the right weekday/hour squares")

# meter() draws to a PhotoImage, so canvas geometry can't be inspected the way bars can;
# this only proves the divider path (ticks=5, as used on the History block bars) renders.
mpar = tk.Frame(root, bg=app.th["surface"])
mpar.pack()
mm = c.App.meter(app, mpar, 0.42, "#d4a24c", ticks=5)
root.update()
check(int(mm["width"]) == app.CW and int(mm["height"]) == app.px(6),
      f"meter with period dividers renders at the expected size ({mm['width']}x{mm['height']})")

# limits card with captured live-shaped account data: email + prepaid must reach the widget tree
sa = type("Stub", (), {})()
for _attr in ("th", "f", "S", "px", "CW", "root", "img", "tip"):
    setattr(sa, _attr, getattr(app, _attr))
sa.cfg = dict(c.DEFAULTS)
sa.args = type("Args", (), {"no_live": False})()
sa.content = tk.Frame(root, bg=app.th["surface"])
sa.content.pack()
for _m in ("card", "lbl", "shape", "meter", "button", "round_corners"):
    setattr(sa, _m, getattr(c.App, _m).__get__(sa, c.App))
sa.connect_statusline = lambda: None
now = 1_700_000_000.0
real_prepaid = c.normalize_prepaid({"amount": 5597, "currency": "EUR",
                                    "balance": {"money": None, "credits": {"amount_minor": 5597, "exponent": 2}}})
s_live = {"now": now, "window": None, "live": {
    "status": "ok", "source": "oauth", "fetched": now - 30, "plan": "Max 20x",
    "email": "person@example.com", "prepaid": real_prepaid, "extra": None,
    "items": [{"key": "seven_day", "label": "Week", "pct": 42.0, "resets": now + 3 * 86400}]}}
c.App.render_limits_card(sa, s_live)
root.update()
texts = []
stack = [sa.content]
while stack:
    wgt = stack.pop()
    try:
        if wgt.winfo_class() == "Label":
            texts.append(str(wgt.cget("text")))
    except Exception:  # noqa: BLE001
        pass
    stack.extend(wgt.winfo_children())
joined = " | ".join(texts)
check("person@example.com" in joined, "limits card shows the account email")
check("Prepaid credits EUR 55.97" in joined, "limits card shows the normalized prepaid balance")


def all_texts(frame):
    out, stack = [], [frame]
    while stack:
        w = stack.pop()
        try:
            cls = w.winfo_class()
            if cls == "Label":
                out.append(str(w.cget("text")))
            elif cls == "Canvas":
                out += [w.itemcget(i, "text") for i in w.find_all() if w.type(i) == "text"]
            stack.extend(w.winfo_children())
        except Exception:  # noqa: BLE001
            pass
    return out


# ---- view stub: scope branches (render_ring_card / render_overview / scope gating) --------
sv = type("Stub", (), {})()
for _attr in ("th", "f", "S", "px", "CW", "root", "img"):
    setattr(sv, _attr, getattr(app, _attr))
sv.tip = type("Tip", (), {"show": lambda self, *a: None, "hide": lambda self, *a: None})()
sv.cfg = dict(c.DEFAULTS)
sv.save_soon = lambda: None
sv._rings = {}
sv.args = type("Args", (), {"no_live": False, "demo": True})()
sv.connect_statusline = lambda: None
sv.content = tk.Frame(root, bg=sv.th["bg"])
sv.content.pack()
for _m in ("card", "lbl", "shape", "chip", "meter", "button", "segmented", "legend", "round_corners",
           "draw_ring", "composition", "no_data", "empty_card", "render_limits_card", "render_kpis",
           "render_scope_hidden", "render_ring_card", "set_cfg", "local_note", "empty_range_hint",
           "bucket_tip"):
    setattr(sv, _m, getattr(c.App, _m).__get__(sv, c.App))
sv.export_csv = lambda: None
for _m in ("render_weekly_emergency", "render_overview_runs", "overview_run_row",
           "goto_live_sessions", "set_tab", "open_settings", "snooze"):
    setattr(sv, _m, getattr(c.App, _m).__get__(sv, c.App))
sv.velocity_line = c.App.velocity_line  # staticmethod: bind nothing
sv.elide = c.App.elide  # ditto: overview run rows elide project names

# R1: scope 'Claude Code' must not leak live-gauge numbers into chip/rows/ring
now2 = 1_700_000_000.0
gw = {"start": now2 - 3600, "end": now2 + 4 * 3600, "src": "live", "agg": [100, 200, 0, 0, 1.25, 7],
      "val": 1.25, "last": now2 - 60, "rate": 0.5, "rate_tokens": 1000.0, "rate_cost_h": 2.0,
      "proj": 3.5, "remaining": 4 * 3600, "elapsed": 0.2, "models": []}
g_live = {"pct": 95.0, "src": "live", "proj_pct": 140.0, "eta": now2 + 3600}
s_loc = {"metric": "cost", "now": now2, "window": gw, "gauge": g_live,
         "limit": 10.0, "limit_src": "custom",
         "live": {"status": "ok", "source": "statusline", "fetched": now2 - 30, "items": []},
         "last_ts": now2 - 60, "has_data": True, "models_today": [],
         "kpi": {"today": {"agg": [0, 0, 0, 0, 1.0, 4]}}}
c.App.render_ring_card(sv, s_loc, force_live=False)
root.update()
jt = " | ".join(all_texts(sv.content))
check("of plan" not in jt, "local scope: ring caption never says 'of plan'")
check("Limit by" not in jt, "local scope: no live-derived 'Limit by …' chip or row")
check(c.fmt_pct(95.0) not in jt, "local scope: the live 95% never reaches the widget")
check(c.fmt_pct(12.5) in jt, f"local scope: ring shows the local percent ({c.fmt_pct(12.5)})")
check("of limit" in jt, "local scope: caption comes from the local limit source")

# Q2a: scope 'Claude (all)' without live data shows 'no plan data', never a local estimate
for w_ in sv.content.winfo_children():
    w_.destroy()
s_all = dict(s_loc, gauge={"pct": 55.0, "src": "auto", "proj_pct": 55.0, "eta": None})
c.App.render_ring_card(sv, s_all, force_live=True, show_models=False, live_only=True)
root.update()
jt = " | ".join(all_texts(sv.content))
check("no plan data" in jt, "all scope without a feed: ring and chip say 'no plan data'")
check(c.fmt_pct(55.0) not in jt, "all scope without a feed: the local fallback percent stays hidden")

# Q1b: log tabs in 'all' scope render the placeholder with both switch buttons
for w_ in sv.content.winfo_children():
    w_.destroy()
c.App.render_scope_hidden(sv, s_all)
root.update()
jt = " | ".join(all_texts(sv.content))
check("account-wide plan numbers only" in jt, "placeholder explains why the tab is hidden")
check("Show Claude Code" in jt and "Show Both" in jt, "placeholder offers both scope switches")

# all three scope branches of render_overview render without raising
demo = c.DemoStore()
now_s = c.time.time()
es = demo.entries(now_s - 31 * 86400)
live_ok = {"status": "ok", "source": "statusline", "fetched": now_s - 30, "plan": "Pro",
           "items": [{"key": "five_hour", "label": "5 hours", "pct": 65.0, "resets": now_s + 3 * 3600},
                     {"key": "seven_day", "label": "Week", "pct": 42.0, "resets": now_s + 3 * 86400}]}
snap_v = c.build_snapshot(es, now_s, cfg, live_ok,
                          {"roots": [], "files": 0, "entries": len(es), "demo": True})
ok = True
for scope in ("both", "all", "local"):
    for w_ in sv.content.winfo_children():
        w_.destroy()
    sv.cfg["scope"] = scope
    try:
        c.App.render_overview(sv, snap_v)
        root.update()
        print("PASS render_overview scope=%s" % scope)
    except Exception as ex:  # noqa: BLE001
        ok = False
        fails.append("render_overview scope=%s: %r" % (scope, ex))
        print("FAIL render_overview scope=%s -> %r" % (scope, ex))
check(ok, "overview renders under all three scopes")

# render_history bails cleanly on an empty snapshot (cumulative mode selected)
for w_ in sv.content.winfo_children():
    w_.destroy()
sv.cfg["hist_mode"] = "cum"
called = {}
sv.empty_card = lambda *a, **k: called.update(title=a[0])
try:
    c.App.render_history(sv, None)
    check(called.get("title") == "Reading your Claude Code logs…",
          "history bails to the empty card when there is no snapshot yet")
except Exception as ex:  # noqa: BLE001
    check(False, f"render_history(None) must not raise (got {ex!r})")

# Q6: the 7-day-avg key lives in the toolbar, not the crowded card header
sv.cfg["hist_range"] = 30
sv.cfg["hist_mode"] = "day"
for w_ in sv.content.winfo_children():
    w_.destroy()
c.App.render_history(sv, snap_v)
root.update()

def descendants(w):
    out = [w]
    for ch in w.winfo_children():
        out += descendants(ch)
    return out

titles = [w for w in descendants(sv.content)
          if w.winfo_class() == "Label" and str(w.cget("text")) == "DAILY USAGE"]
check(bool(titles), "history renders the daily chart card")
if titles:
    chart_head = titles[0].master
    check("7-day avg" not in all_texts(chart_head),
          "the avg key stays out of the card header where 4+ model families already crowd it")
avg_lbls = [w for w in descendants(sv.content)
            if w.winfo_class() == "Label" and str(w.cget("text")) == "7-day avg"]
check(len(avg_lbls) == 1 and avg_lbls[0].master.master.master is sv.content,
      "the avg key sits in the toolbar row")
if avg_lbls:
    check(avg_lbls[0].master.master.winfo_reqwidth() <= sv.CW,
          "toolbar row (mode toggle + avg key) fits the card width")
for w_ in sv.content.winfo_children():
    w_.destroy()
sv.cfg["hist_mode"] = "cum"
c.App.render_history(sv, snap_v)
root.update()
hints = [w for w in descendants(sv.content)
         if w.winfo_class() == "Label" and "flat stretches are gaps" in str(w.cget("text"))]
check(len(hints) == 1 and hints[0].master is sv.content,
      "cumulative hint sits on its own full-width line, not in the toolbar")
check(bool(hints) and hints[0].winfo_reqwidth() <= sv.CW,
      "cumulative hint fits the card width")

# ---- live sessions view: KPI strip, filter bar, accordion groups, inspector ----
ss = type("Stub", (), {})()
for _attr in ("th", "f", "S", "px", "CW", "root", "img"):
    setattr(ss, _attr, getattr(app, _attr))
ss.tip = type("Tip", (), {"show": lambda self, *a: None, "hide": lambda self, *a: None})()
ss.cfg = dict(c.DEFAULTS)
ss.save_soon = lambda: None
ss.render = lambda: None
ss._rings = {}
ss._sess_query, ss._sess_state, ss._sess_fam = "", "all", "all"
ss._sess_expanded, ss._sess_selected, ss._sess_entry = {}, None, None
ss.content = tk.Frame(root, bg=ss.th["bg"])
ss.content.pack()
for _m in ("card", "lbl", "shape", "chip", "meter", "button", "segmented", "legend", "round_corners",
           "no_data", "empty_card", "local_note", "empty_range_hint",
           "render_sessions", "render_session_kpis", "render_session_filters",
           "render_session_group", "render_session_run", "session_selection",
           "render_session_inspector", "set_sess_state", "set_sess_fam"):
    setattr(ss, _m, getattr(c.App, _m).__get__(ss, c.App))
ss.elide = c.App.elide  # staticmethod: bind nothing, or every call gains a phantom self
try:
    c.App.render_sessions(ss, snap_v)
    root.update()
    jt = " | ".join(all_texts(ss.content))
    check("Live now" in jt and "Top group" in jt, "sessions KPI strip renders live/top-group cells")
    check("7 days" in jt and "30 days" in jt, "sessions KPI strip renders period cells")
    check("PROJECT & BRANCH GROUPS" in jt, "sessions accordion card renders")
    check("SESSION DETAIL" in jt, "inspector renders for the default-selected run")
    check("TOKEN LEGS" in jt and "Cache hit" in jt,
          "inspector shows the token-leg waterfall and cache insight")
    proj0 = snap_v["groups"][0]["project"]
    check(proj0 in jt, f"richest group project reaches the widget ({proj0})")
except Exception as ex:  # noqa: BLE001
    check(False, f"render_sessions must not raise (got {ex!r})")
# filter with no hits shows the honest empty card, never a blank tab
for w_ in ss.content.winfo_children():
    w_.destroy()
ss._sess_query = "nothing-matches-here-zzz"
ss._sess_expanded, ss._sess_selected = {}, None
try:
    c.App.render_sessions(ss, snap_v)
    root.update()
    jt = " | ".join(all_texts(ss.content))
    check("NO MATCHING RUNS" in jt, "a filter with no hits explains itself")
except Exception as ex:  # noqa: BLE001
    check(False, f"render_sessions with empty filter must not raise (got {ex!r})")
# state pills render through the same path without raising
ss._sess_query = ""
for _state in ("running", "completed"):
    for w_ in ss.content.winfo_children():
        w_.destroy()
    ss._sess_state = _state
    ss._sess_expanded, ss._sess_selected = {}, None
    try:
        c.App.render_sessions(ss, snap_v)
        root.update()
        jt = " | ".join(all_texts(ss.content))
        check("PROJECT & BRANCH GROUPS" in jt or "NO MATCHING RUNS" in jt,
              f"state={_state} renders groups or the honest empty card")
    except Exception as ex:  # noqa: BLE001
        check(False, f"render_sessions state={_state} must not raise (got {ex!r})")
ss._sess_state = "all"

# ---- overview revamp: headroom, emergency card, velocity line, run cards ----
for w_ in sv.content.winfo_children():
    w_.destroy()
sv.cfg["scope"] = "both"
try:
    c.App.render_overview(sv, snap_v)
    root.update()
    jt = " | ".join(all_texts(sv.content))
    check("Headroom" in jt, "ring card carries the headroom row")
    check("tok/h" in jt and "cache hit" in jt, "24h chart carries the velocity sentence")
    check("RECENT RUNS" in jt and "Open Live Sessions" in jt,
          "overview lists recent runs with a cross-link")
    check("LIVE RIGHT NOW" in jt, "live demo runs surface on the overview")
except Exception as ex:  # noqa: BLE001
    check(False, f"render_overview with run cards must not raise (got {ex!r})")

# emergency card: only weeklies at 90%+, with review + snooze actions
now3 = 1_700_000_000.0
s_em = {"now": now3, "live": {"status": "ok", "items": [
    {"key": "seven_day_opus", "label": "Week · Opus", "pct": 93.0, "resets": now3 + 86400}]}}
for w_ in sv.content.winfo_children():
    w_.destroy()
try:
    shown = c.App.render_weekly_emergency(sv, s_em)
    root.update()
    jt = " | ".join(all_texts(sv.content))
    check(shown is True and "WEEKLY CAP CRITICAL" in jt, "a 93% weekly raises the emergency card")
    check("Review thresholds" in jt and "Snooze 1h" in jt,
          "emergency card offers review and snooze, not a kill switch")
except Exception as ex:  # noqa: BLE001
    check(False, f"render_weekly_emergency must not raise (got {ex!r})")
s_calm = {"now": now3, "live": {"status": "ok", "items": [
    {"key": "seven_day", "label": "Week", "pct": 41.0, "resets": now3 + 86400},
    {"key": "five_hour", "label": "5 hours", "pct": 99.0, "resets": now3 + 3600}]}}
for w_ in sv.content.winfo_children():
    w_.destroy()
try:
    shown = c.App.render_weekly_emergency(sv, s_calm)
    root.update()
    check(shown is False and all_texts(sv.content) == [],
          "41% weekly (even with 99% 5-hour) renders nothing")
except Exception as ex:  # noqa: BLE001
    check(False, f"render_weekly_emergency calm path must not raise (got {ex!r})")

root.destroy()
print("FAILURES:", fails if fails else "none")
