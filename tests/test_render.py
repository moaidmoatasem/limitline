"""Render-path checks for the chart widgets (needs a display; skips cleanly without one).

Run: python tests/test_render.py ; must end with `FAILURES: none`.
"""
import os, sys
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
check("person@example.com" in joined, f"limits card shows the account email")
check("Prepaid credits EUR 55.97" in joined, f"limits card shows the normalized prepaid balance")

root.destroy()
print("FAILURES:", fails if fails else "none")
