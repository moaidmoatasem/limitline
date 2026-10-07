#!/usr/bin/env python3
"""
Limitline - a floating desktop monitor for your Claude Code usage
=====================================================================

What it shows
  - Current 5-hour window: how much is used (live from your plan when available,
    otherwise estimated against your busiest past window), reset countdown,
    burn rate, where you'll land by the reset, and when you'd hit the limit.
  - Live plan limits (5-hour and weekly) taken from Claude Code's official status
    line - no login or token involved. Optional advanced mode adds per-model
    weekly limits using Claude Code's saved login (see Settings; read the warning).
  - Today / 7-day / 30-day totals with API-equivalent cost.
  - Last-24-hours and daily charts stacked by model, an hour-of-week heatmap,
    recent 5-hour windows, and per-project / per-session breakdowns.
  - Alerts at the thresholds you choose (banner + desktop notification) and a
    heads-up when your window resets.

How it works
  Reads the session logs Claude Code keeps on this computer
  (~/.claude/projects, ~/.config/claude/projects, or $CLAUDE_CONFIG_DIR)
  incrementally, in the background. Live plan limits come from a small file that
  Claude Code's status-line hook writes (connect it once: --install-statusline or
  Settings > Connect). Nothing leaves your machine unless you opt in to the
  advanced saved-login mode.

Run
  python limitline.py          (Windows tip: use pythonw, or rename to .pyw)
  python limitline.py --demo   (preview with sample data)

Options
  --mini              start collapsed to the small pill
  --theme dark|light  colour theme
  --refresh SEC       rescan interval in seconds (default 15)
  --path DIR          extra log folder to include (repeatable)
  --no-live           don't fetch live plan limits this run
  --reset             forget saved settings
  --multi             allow more than one copy to run
  --install-statusline    connect live limits (edits Claude Code's settings.json, backed up)
  --uninstall-statusline  undo that

Controls
  Drag the title bar to move it; double-click it (or press M / Esc) for the pill.
  R refresh - T always on top - S settings - 1-4 tabs - Ctrl+Q quit
  Right-click anywhere for the menu (export CSV, open logs folder, ...).
  Hover charts, rings and buttons for details.

Settings live in ~/.limitline.json. Prices (USD per million tokens)
can be overridden there, e.g. "price_overrides": {"opus": [4, 5, 8, 0.2, 20]}
meaning [input, cache write 5m, cache write 1h, cache read, output].

Standard library only - Python 3.8+ with tkinter.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import operator
import os
import queue
import random
import re
import shlex
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone

try:
    import tkinter as tk
    import tkinter.font as tkfont
    from tkinter import filedialog
except ImportError:  # pragma: no cover - reported in main()
    tk = None
_Canvas = tk.Canvas if tk else object

APP_NAME = "Limitline"
VERSION = "2.3.1"
IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
HOME = os.path.expanduser("~")
CONFIG_PATH = os.path.join(HOME, ".limitline.json")
WINDOW_SEC = 5 * 3600
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
INSTANCE_PORT = 47613

# =============================================================================
# Settings
# =============================================================================
DEFAULTS = {
    "theme": "dark",            # dark | light
    "accent": "gold",           # gold | claude | ocean | forest | violet
    "opacity": 0.97,
    "topmost": True,
    "frameless": not IS_MAC,    # custom title bar instead of the system one
    "mini": False,
    "tab": "overview",
    "x": None,
    "y": None,
    "metric": "cost",           # cost | tokens | io
    "limit_mode": "auto",       # auto (busiest past window) | custom
    "limit_value": 0.0,         # $ when metric is cost, otherwise tokens
    "refresh_sec": 15,
    "history_days": 30,
    "alerts": True,
    "alert_levels": [75, 90],           # 5-hour window
    "alert_levels_week": [50, 75, 90],  # weekly limits
    "alert_step": 0,                    # also alert every N% (0 = off, e.g. 25 -> 25, 50, 75, 100)
    "alert_forecast": True,             # "at this pace you'll hit the limit at ..."
    "quiet_enabled": False,
    "quiet_from": "22:00",
    "quiet_to": "08:00",
    "snooze_until": 0.0,
    "alert_sound": False,
    "mascot": "subtle",                 # off | subtle | full
    "mascot_animate": True,
    "desktop_notify": True,
    "notify_reset": True,
    "welcomed": False,          # first-run welcome window has been shown
    "live_limits": True,
    "live_oauth": False,        # advanced, off by default: ask Anthropic using Claude Code's saved login
    "live_interval_sec": 120,
    "extra_paths": [],
    "price_overrides": {},
    "hist_range": 14,
    "proj_range": "7d",
    "alerted": {},
    "alerts_pace_only": False,  # only alert when usage is running ahead of the clock
    "on_alert_command": "",     # shell command run on alerts (env: LIMITLINE_EVENT/LABEL/PCT)
    "on_reset_command": "",     # shell command run when a near-full window resets
}


def load_config(reset=False):
    cfg = json.loads(json.dumps(DEFAULTS))
    if reset:
        return cfg
    data = {}
    for path in (CONFIG_PATH, os.path.join(os.path.dirname(CONFIG_PATH), ".claude-usage-popup.json")):
        try:    # the second path is the pre-rename settings file
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            break
        except (OSError, ValueError):
            continue
    if isinstance(data, dict):
        for k, v in data.items():
            if k not in cfg:
                continue
            d = cfg[k]
            if d is None or v is None or type(v) is type(d) or (isinstance(d, float) and type(v) is int):
                cfg[k] = v
    # sanity
    cfg["opacity"] = min(1.0, max(0.4, float(cfg["opacity"])))
    cfg["refresh_sec"] = min(600, max(5, int(cfg["refresh_sec"])))
    cfg["history_days"] = min(180, max(7, int(cfg["history_days"])))
    if cfg["tab"] not in ("overview", "history", "projects", "sessions"):
        cfg["tab"] = "overview"
    if cfg["metric"] not in ("cost", "tokens", "io"):
        cfg["metric"] = "cost"
    if cfg["hist_range"] not in (7, 14, 30):
        cfg["hist_range"] = 14
    if cfg["proj_range"] not in ("today", "7d", "30d"):
        cfg["proj_range"] = "7d"
    try:
        cfg["alert_levels"] = sorted({min(100, max(1, int(x))) for x in cfg["alert_levels"]})
    except (TypeError, ValueError):
        cfg["alert_levels"] = [75, 90]
    try:
        cfg["limit_value"] = max(0.0, float(cfg["limit_value"] or 0))
    except (TypeError, ValueError):
        cfg["limit_value"] = 0.0
    if not isinstance(cfg["alerted"], dict):
        cfg["alerted"] = {}
    try:
        cfg["alert_levels_week"] = sorted({min(100, max(1, int(x))) for x in cfg["alert_levels_week"]})
    except (TypeError, ValueError):
        cfg["alert_levels_week"] = [50, 75, 90]
    try:
        step = int(cfg["alert_step"])
    except (TypeError, ValueError):
        step = 0
    cfg["alert_step"] = 0 if step < 5 else min(50, step)
    for k, dflt in (("quiet_from", "22:00"), ("quiet_to", "08:00")):
        if not (isinstance(cfg[k], str) and re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", cfg[k].strip())):
            cfg[k] = dflt
    if cfg["mascot"] not in ("off", "subtle", "full"):
        cfg["mascot"] = "subtle"
    try:
        cfg["snooze_until"] = float(cfg["snooze_until"] or 0)
    except (TypeError, ValueError):
        cfg["snooze_until"] = 0.0
    return cfg


def save_config(cfg):
    try:
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
        os.replace(tmp, CONFIG_PATH)
    except OSError:
        pass


# =============================================================================
# Formatting & small helpers
# =============================================================================
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
METRIC_NAME = {"cost": "API-equivalent cost", "tokens": "all tokens", "io": "input + output tokens"}


def _int(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def fmt_tokens(n):
    n = float(n or 0)
    a = abs(n)
    if a >= 1e9:
        return f"{n / 1e9:.2f}B"
    if a >= 1e7:
        return f"{n / 1e6:.1f}M"
    if a >= 1e6:
        return f"{n / 1e6:.2f}M"
    if a >= 1e5:
        return f"{n / 1e3:.0f}k"
    if a >= 1e3:
        return f"{n / 1e3:.1f}k"
    return f"{n:.0f}"


def fmt_cost(c):
    c = float(c or 0)
    if c == 0:
        return "$0"
    if c < 0.01:
        return "<$0.01"
    if c < 1000:
        return f"${c:,.2f}"
    return f"${c:,.0f}"


def fmt_metric(v, metric):
    return fmt_cost(v) if metric == "cost" else fmt_tokens(v)


def fmt_axis(v, metric):
    if metric == "cost":
        if v >= 10:
            return f"${v:,.0f}"
        return "$" + f"{v:.2f}".rstrip("0").rstrip(".")
    if v >= 1e9:
        return f"{v / 1e9:g}B"
    if v >= 1e6:
        return f"{v / 1e6:g}M"
    if v >= 1e3:
        return f"{v / 1e3:g}k"
    return f"{v:g}"


def fmt_dur(sec):
    sec = max(0, int(sec))
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m"
    return f"{sec}s"


def fmt_ago(sec):
    return "just now" if sec < 60 else fmt_dur(sec) + " ago"


def local_day(ts):
    lt = time.localtime(ts)
    return date(lt.tm_year, lt.tm_mon, lt.tm_mday).toordinal()


def day_start(ordinal):
    d = date.fromordinal(ordinal)
    return time.mktime((d.year, d.month, d.day, 0, 0, 0, 0, 0, -1))


def hour_start(ts):
    lt = time.localtime(ts)
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, lt.tm_hour, 0, 0, 0, 0, -1))


def fmt_clock(ts):
    return time.strftime("%H:%M", time.localtime(ts))


def fmt_date(ordinal, weekday=True):
    d = date.fromordinal(ordinal)
    s = f"{d.day} {MONTHS[d.month - 1]}"
    return f"{WEEKDAYS[d.weekday()]} {s}" if weekday else s


def day_label(ordinal, today):
    if ordinal == today:
        return "Today"
    if ordinal == today - 1:
        return "Yesterday"
    return fmt_date(ordinal)


def fmt_when(ts, now):
    dd = local_day(ts) - local_day(now)
    clock = fmt_clock(ts)
    if dd == 0:
        return clock
    if dd == 1:
        return "tomorrow " + clock
    if dd == -1:
        return "yesterday " + clock
    if 1 < dd < 7:
        return WEEKDAYS[date.fromordinal(local_day(ts)).weekday()] + " " + clock
    return fmt_date(local_day(ts), weekday=False) + " " + clock


def parse_ts(s):
    if not isinstance(s, str) or len(s) < 19:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        try:
            return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            return None


def parse_amount(text):
    """'5M' -> 5e6, '$12.5' -> 12.5, '250k' -> 250000."""
    t = str(text or "").strip().lower().replace("$", "").replace(",", "").replace(" ", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([kmb]?)", t)
    if not m:
        return 0.0
    return float(m.group(1)) * {"": 1, "k": 1e3, "m": 1e6, "b": 1e9}[m.group(2)]


def nice_scale(mx, n=3):
    if mx <= 0:
        return 1.0, 1.0
    raw = mx / n
    mag = 10 ** math.floor(math.log10(raw))
    step = mag
    for m in (1, 2, 2.5, 5, 10):
        step = m * mag
        if step >= raw:
            break
    return step, math.ceil(mx / step - 1e-9) * step


def _rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(c):
    return "#%02x%02x%02x" % c


def mix(a, b, t):
    """Blend colour a towards b by t (0..1)."""
    ca, cb = _rgb(a), _rgb(b)
    return _hex(tuple(int(round(ca[i] + (cb[i] - ca[i]) * t)) for i in range(3)))


def ramp(stops, t):
    t = max(0.0, min(1.0, t))
    n = len(stops) - 1
    i = min(int(t * n), n - 1)
    return mix(stops[i], stops[i + 1], t * n - i)


def shorten_path(p):
    return "~" + p[len(HOME):] if p.startswith(HOME) else p


# =============================================================================
# Models & pricing  (USD per million tokens, from Anthropic's published prices)
# =============================================================================
FAMS = ("opus", "sonnet", "haiku", "fable", "other")
FAM_LABEL = {"opus": "Opus", "sonnet": "Sonnet", "haiku": "Haiku", "fable": "Fable", "other": "Other"}
_META = {}


def base_price(fam, ver):
    """-> (input, cache write 5m, cache write 1h, cache read, output)."""
    v = tuple(ver) + (0,) * (2 - len(ver)) if ver else (99, 0)  # unknown version -> newest
    if fam in ("fable", "mythos"):
        return (10.0, 12.5, 20.0, 0.25 if v >= (5, 1) else 1.0, 50.0)
    if fam == "opus":
        if v >= (5, 5):
            return (4.0, 5.0, 8.0, 0.20, 20.0)
        if v >= (4, 5):
            return (5.0, 6.25, 10.0, 0.50, 25.0)
        return (15.0, 18.75, 30.0, 1.50, 75.0)
    if fam == "sonnet":
        if v >= (5, 0):
            return (2.0, 2.5, 4.0, 0.20, 10.0)
        return (3.0, 3.75, 6.0, 0.30, 15.0)
    if fam == "haiku":
        if v >= (4, 5):
            return (1.0, 1.25, 2.0, 0.10, 5.0)
        if v >= (3, 5):
            return (0.8, 1.0, 1.6, 0.08, 4.0)
        return (0.25, 0.30, 0.50, 0.03, 1.25)
    return (2.0, 2.5, 4.0, 0.20, 10.0)  # unknown model: assume Sonnet-class


def model_meta(model):
    """-> (family group, display name, price tuple)."""
    meta = _META.get(model)
    if meta:
        return meta
    m = (model or "unknown").lower()
    raw = next((f for f in ("fable", "mythos", "opus", "sonnet", "haiku") if f in m), "other")
    nums = tuple(int(n) for n in re.findall(r"\d+", m) if len(n) <= 2)[:2]
    if raw == "other":
        disp = re.sub(r"^claude-", "", m)[:22] or "unknown"
    else:
        disp = raw.capitalize() + (" " + ".".join(str(n) for n in nums) if nums else "")
    fam = "fable" if raw == "mythos" else raw
    meta = _META[model] = (fam, disp, base_price(raw, nums))
    return meta


LATEST_PRICED = {"opus": (5, 5), "sonnet": (5, 5), "haiku": (4, 5), "fable": (5, 1)}


def price_status(model):
    """None when the model is covered by the price table, else a short reason."""
    m = (model or "unknown").lower()
    raw = next((f for f in ("fable", "mythos", "opus", "sonnet", "haiku") if f in m), None)
    if raw is None:
        return "unrecognised model"
    fam = "fable" if raw == "mythos" else raw
    nums = tuple(int(n) for n in re.findall(r"\d+", m) if len(n) <= 2)[:2]
    if not nums:
        return "version not recognised"
    v = nums + (0,) * (2 - len(nums))
    if v > LATEST_PRICED[fam]:
        return "newer than the price table"
    return None


def usage_cost(price, u):
    pin, p5, p1, pcr, pout = price
    inp, out = _int(u.get("input_tokens")), _int(u.get("output_tokens"))
    cw, cr = _int(u.get("cache_creation_input_tokens")), _int(u.get("cache_read_input_tokens"))
    cc = u.get("cache_creation") if isinstance(u.get("cache_creation"), dict) else {}
    w1 = min(cw, _int(cc.get("ephemeral_1h_input_tokens")))
    cost = (inp * pin + out * pout + (cw - w1) * p5 + w1 * p1 + cr * pcr) / 1e6
    if u.get("speed") == "fast":
        cost *= 2.0
    if u.get("inference_geo") == "us":
        cost *= 1.1
    stu = u.get("server_tool_use")
    if isinstance(stu, dict):
        cost += _int(stu.get("web_search_requests")) * 0.01
    return cost


# =============================================================================
# Log store (incremental JSONL reader)
# =============================================================================
class Entry:
    __slots__ = ("ts", "model", "fam", "disp", "inp", "out", "cw", "cr", "cost",
                 "project", "session", "day", "hour", "wday")


def make_entry(ts, model, fam, disp, inp, out, cw, cr, cost, project, session):
    e = Entry()
    e.ts, e.model, e.fam, e.disp = ts, model, fam, disp
    e.inp, e.out, e.cw, e.cr, e.cost = inp, out, cw, cr, cost
    e.project, e.session = project, session
    lt = time.localtime(ts)
    e.day = date(lt.tm_year, lt.tm_mon, lt.tm_mday).toordinal()
    e.hour, e.wday = lt.tm_hour, lt.tm_wday
    return e


def log_roots(extra=()):
    cands = []
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:  # Claude Code uses only this folder when it's set
        cands += [os.path.join(p.strip(), "projects") for p in env.split(",") if p.strip()]
    else:
        cands += [os.path.join(HOME, ".config", "claude", "projects"), os.path.join(HOME, ".claude", "projects")]
    for p in extra or ():
        p = os.path.expanduser(str(p).strip())
        if p:
            cands.append(os.path.join(p, "projects") if os.path.isdir(os.path.join(p, "projects")) else p)
    out, seen = [], set()
    for c in cands:
        r = os.path.realpath(c)
        if r not in seen and os.path.isdir(r):
            seen.add(r)
            out.append(r)
    return out


_TS = operator.attrgetter("ts")


class LogStore:
    demo = False

    def __init__(self, overrides=None):
        self.files = {}    # path -> [size, mtime, offset]
        self.by_key = {}   # dedupe key -> Entry
        self.cost_states = {}  # session id -> (Claude Code's own total, our logged cost at that moment)
        self.overrides = {str(k).lower(): v for k, v in (overrides or {}).items()}
        self._meta = {}
        self.unpriced = {}  # model -> reason, for models priced by assumption
        self._pruned = time.time()

    def meta(self, model):
        m = self._meta.get(model)
        if m is None:
            fam, disp, price = model_meta(model)
            ov = (self.overrides.get(model.lower()) or self.overrides.get(disp.lower())
                  or self.overrides.get(fam))
            if isinstance(ov, (list, tuple)) and len(ov) == 5:
                try:
                    price = tuple(float(x) for x in ov)
                except (TypeError, ValueError):
                    pass
            m = self._meta[model] = (fam, disp, price)
            why = price_status(model)
            if why and not (isinstance(ov, (list, tuple)) and len(ov) == 5):
                self.unpriced[model] = why
        return m

    def scan(self, roots, since, progress=None):
        paths = []
        for root in roots:
            for dp, _dirs, files in os.walk(root):
                for fn in files:
                    if fn.endswith(".jsonl"):
                        paths.append(os.path.join(dp, fn))
        changed = 0
        for i, p in enumerate(paths):
            try:
                st = os.stat(p)
            except OSError:
                continue
            if st.st_mtime < since:
                continue
            rec = self.files.get(p)
            if rec and rec[0] == st.st_size and rec[1] == st.st_mtime:
                continue
            start = rec[2] if rec and st.st_size >= rec[2] else 0
            self.files[p] = [st.st_size, st.st_mtime, self._read(p, start)]
            changed += 1
            if progress and changed % 20 == 0:
                progress(i, len(paths))
        if time.time() - self._pruned > 3600:
            self._pruned = time.time()
            self.by_key = {k: e for k, e in self.by_key.items() if e.ts >= since}
        return changed, len(paths)

    def _read(self, path, start):
        pos = start
        try:
            with open(path, "rb") as fh:
                if start:
                    fh.seek(start)
                for raw in fh:
                    if not raw.endswith(b"\n"):
                        break  # incomplete line - pick it up next time
                    pos += len(raw)
                    if b'"usage"' in raw and b'"assistant"' in raw:
                        self._parse(raw, path)
                    elif b'"cost-state"' in raw:
                        self._parse_cost_state(raw)
        except OSError:
            pass
        return pos

    def _parse(self, raw, path):
        try:
            d = json.loads(raw)
        except ValueError:
            return
        if not isinstance(d, dict) or d.get("type") != "assistant":
            return
        msg = d.get("message")
        if not isinstance(msg, dict):
            return
        u = msg.get("usage")
        if not isinstance(u, dict):
            return
        model = str(msg.get("model") or "unknown")
        if model.startswith("<"):  # <synthetic> placeholder messages
            return
        inp, out = _int(u.get("input_tokens")), _int(u.get("output_tokens"))
        cw, cr = _int(u.get("cache_creation_input_tokens")), _int(u.get("cache_read_input_tokens"))
        if not (inp or out or cw or cr):
            return
        ts = parse_ts(d.get("timestamp"))
        if ts is None:
            return
        mid, rid = msg.get("id"), d.get("requestId")
        key = (mid, rid) if (mid or rid) else (d.get("uuid") or raw[:96])
        fam, disp, price = self.meta(model)
        c = d.get("costUSD")
        cost = float(c) if isinstance(c, (int, float)) and not isinstance(c, bool) else usage_cost(price, u)
        e = make_entry(ts, sys.intern(model), fam, disp, inp, out, cw, cr, cost,
                       self._project(d.get("cwd"), path), sys.intern(str(d.get("sessionId") or "?")))
        old = self.by_key.get(key)
        if old is None or out >= old.out:   # same message logged per content block - keep one
            self.by_key[key] = e

    def _parse_cost_state(self, raw):
        """Claude Code's own running total per session - includes requests the logs miss."""
        try:
            d = json.loads(raw)
        except ValueError:
            return
        if isinstance(d, dict) and d.get("type") == "cost-state" and d.get("sessionId"):
            c = d.get("totalCostUSD")
            if isinstance(c, (int, float)):
                sid = str(d["sessionId"])
                # Claude Code writes this total at one moment while the log keeps growing, so compare it
                # with what the log held *at that point* (the line is read in file order).
                logged = sum(e.cost for e in self.by_key.values() if e.session == sid)
                self.cost_states[sid] = (float(c), logged)

    @staticmethod
    def _project(cwd, path):
        if isinstance(cwd, str) and cwd.strip():
            p = cwd.strip().rstrip("\\/")
            if os.path.normcase(os.path.normpath(p)) == os.path.normcase(os.path.normpath(HOME)):
                return "~ (home)"
            return sys.intern(re.split(r"[\\/]", p)[-1] or p)
        folder = os.path.basename(os.path.dirname(path))
        return sys.intern(folder.strip("-").split("-")[-1] or folder or "unknown")

    def entries(self, since):
        es = [e for e in self.by_key.values() if e.ts >= since]
        es.sort(key=_TS)
        return es


class DemoStore(LogStore):
    """Plausible sample data so the widget can be previewed without logs."""
    demo = True
    PROJECTS = ["api-test-suite", "web-dashboard", "data-pipeline", "mobile-app", "docs-site", "infra-scripts"]
    MODELS = [("claude-sonnet-5-5", 0.60), ("claude-opus-5-5", 0.32), ("claude-haiku-4-5", 0.05),
              ("claude-fable-5-1", 0.03)]

    def __init__(self):
        super().__init__()
        self.rng = random.Random(42)
        self.now0 = time.time()
        self._n = 0
        self._live_sid = None
        self._generate()
        self._tick = time.time()

    def _pick_model(self):
        r, acc = self.rng.random(), 0.0
        for m, p in self.MODELS:
            acc += p
            if r <= acc:
                return m
        return self.MODELS[0][0]

    def _add(self, ts, model, project, sid, inp, out, cw, cr):
        fam, disp, price = self.meta(model)
        u = {"input_tokens": inp, "output_tokens": out, "cache_creation_input_tokens": cw,
             "cache_read_input_tokens": cr, "cache_creation": {"ephemeral_1h_input_tokens": cw}}
        self._n += 1
        self.by_key[("demo", self._n)] = make_entry(ts, model, fam, disp, inp, out, cw, cr,
                                                    usage_cost(price, u), project, sid)

    def _session(self, start, minutes, model=None, project=None):
        rng = self.rng
        model = model or self._pick_model()
        project = project or rng.choice(self.PROJECTS)
        sid = "demo-%08x" % rng.getrandbits(32)
        t, end, ctx = start, start + minutes * 60, rng.randint(18000, 42000)
        while t < end and t < self.now0:
            out = int(min(9000, rng.lognormvariate(5.9, 0.9)))
            cw = rng.choice([0, 0, 0, rng.randint(1500, 22000)])
            ctx += out + rng.randint(300, 5000)
            if ctx > 190000:
                ctx = rng.randint(25000, 45000)
                cw = ctx
            m = model if rng.random() > 0.07 else "claude-haiku-4-5"
            self._add(t, m, project, sid, rng.randint(2, 60), out, cw, ctx)
            t += rng.uniform(14, 100)
        return sid

    def _generate(self):
        rng, today = self.rng, local_day(self.now0)
        for back in range(34, 0, -1):
            ds = day_start(today - back)
            weekend = date.fromordinal(today - back).weekday() >= 5
            for _ in range(rng.choice([0, 1, 1, 2] if weekend else [1, 2, 2, 3, 3, 4])):
                hour = rng.choice([9, 10, 10, 11, 12, 14, 14, 15, 16, 17, 20, 21, 22])
                self._session(ds + hour * 3600 + rng.randint(0, 3000), rng.randint(15, 140))
        self._session(self.now0 - 4.1 * 3600, 55, "claude-opus-5-5", "web-dashboard")
        self._session(self.now0 - 2.6 * 3600, 40, "claude-sonnet-5-5", "api-test-suite")
        self._live_sid = self._session(self.now0 - 52 * 60, 52, "claude-sonnet-5-5", "data-pipeline")

    def scan(self, roots, since, progress=None):
        now = time.time()
        if now - self._tick > 15:  # keep the demo "alive"
            self._tick = self.now0 = now
            for k in range(self.rng.randint(1, 3)):
                self._add(now - k * 4, "claude-sonnet-5-5", "data-pipeline", self._live_sid,
                          4, self.rng.randint(150, 1600), 0, self.rng.randint(90000, 160000))
        return 0, 0


# =============================================================================
# Live plan limits (same source as Claude Code's /usage)
# =============================================================================
LIVE_LABELS = {"seven_day_fable": "Week · Fable", "seven_day_cowork": "Week · Cowork", "five_hour": "Session · 5h", "seven_day": "Week · all models", "seven_day_opus": "Week · Opus",
               "seven_day_sonnet": "Week · Sonnet", "seven_day_oauth_apps": "Week · other apps"}
LIVE_ORDER = ["five_hour", "seven_day", "seven_day_sonnet", "seven_day_opus", "seven_day_oauth_apps"]


# =============================================================================
# Official live-limits source: Claude Code's status line
#   Claude Code documents a status-line hook that receives rate_limits (5-hour and
#   7-day percentage + reset time) on stdin. `--statusline` stores just that small
#   block in a local file; the app reads the file. No login or token is touched.
# =============================================================================
def live_file_path():
    return os.path.join(os.path.dirname(CONFIG_PATH), ".limitline-live.json")


def claude_settings_path():
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    base = env.split(",")[0].strip() if env and env.strip() else os.path.join(HOME, ".claude")
    return os.path.join(base, "settings.json")


def _backup_path():
    return os.path.join(os.path.dirname(CONFIG_PATH), ".limitline-statusline-backup.json")


def _write_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def _shell_join(parts):
    return subprocess.list2cmdline(parts) if IS_WIN else " ".join(shlex.quote(x) for x in parts)


def _status_python():
    """The interpreter for the status line. Never pythonw.exe: it has no stdin/stdout, so Claude Code would get nothing."""
    exe = sys.executable
    if IS_WIN:
        d, name = os.path.split(exe)
        if name.lower() == "pythonw.exe" and os.path.exists(os.path.join(d, "python.exe")):
            exe = os.path.join(d, "python.exe")
        exe = exe.replace("\\", "/")     # forward slashes survive both cmd.exe and Git Bash
    return exe


def statusline_command(chain=None, config_dir=None):
    script = os.path.abspath(__file__)
    parts = [_status_python(), script.replace("\\", "/") if IS_WIN else script, "--statusline"]
    if config_dir:
        parts += ["--config-dir", config_dir]
    if chain:
        parts += ["--then", chain]
    return _shell_join(parts)


def run_statusline(chain=None):
    """Claude Code status-line command: save rate_limits, print one short line (or the chained command's)."""
    try:
        raw = sys.stdin.read() if sys.stdin else ""
    except (OSError, ValueError):
        raw = ""
    try:
        d = json.loads(raw)
    except ValueError:
        d = None
    if isinstance(d, dict) and isinstance(d.get("rate_limits"), dict):
        try:
            _write_json_atomic(live_file_path(), {"ts": time.time(), "rate_limits": d["rate_limits"]})
        except OSError as ex:
            _statusline_note(f"could not write {live_file_path()}: {ex}")
    elif raw.strip():
        _statusline_note("Claude Code sent no rate_limits (needs a Pro/Max login and a first reply; "
                         "keys received: %s)" % (sorted(d)[:12] if isinstance(d, dict) else "unreadable input"))
    out = ""
    if chain:
        try:
            r = subprocess.run(chain, shell=True, input=raw, capture_output=True, text=True, timeout=5)
            out = r.stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
    elif isinstance(d, dict):
        rl = d.get("rate_limits") or {}
        bits = []
        for key, tag in (("five_hour", "5h"), ("seven_day", "7d")):
            v = (rl.get(key) or {}).get("used_percentage")
            if isinstance(v, (int, float)):
                bits.append(f"{tag} {v:.0f}%")
        out = " · ".join(bits)
    if sys.stdout:
        sys.stdout.write(out)


def _statusline_note(text):
    """Last status-line problem, for 'why is there no live data?' (kept next to the config)."""
    try:
        with open(os.path.join(os.path.dirname(CONFIG_PATH), ".limitline-statusline-note.txt"), "w", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")
    except OSError:
        pass


def _chain_of(cmd):
    """The original status line we wrapped, taken back out of our own command."""
    i = cmd.find(" --then ")
    if i < 0:
        return None
    rest = cmd[i + 8:].strip()
    if rest.startswith('"') and rest.endswith('"') and len(rest) > 1:
        rest = rest[1:-1].replace('\\"', '"')
    elif rest.startswith("'") and rest.endswith("'") and len(rest) > 1:
        rest = rest[1:-1].replace("'\"'\"'", "'")
    return rest or None


def install_statusline(config_dir=None):
    """Point Claude Code's status line at us (keeping any existing one running). -> message"""
    sp = claude_settings_path()
    try:
        with open(sp, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return False, f"{sp} isn't a JSON object; left untouched."
    except FileNotFoundError:
        data = {}
    except (OSError, ValueError):
        return False, f"Couldn't read {sp}; left untouched."
    cur = data.get("statusLine")
    if isinstance(cur, dict) and "--statusline" in str(cur.get("command", "")):
        old = str(cur.get("command", ""))
        fresh = statusline_command(_chain_of(old), config_dir)
        if old == fresh:
            return True, "Already connected."
        try:                      # same app, but a stale path/interpreter (e.g. pythonw): repair in place
            data["statusLine"] = dict(cur, type="command", command=fresh)
            _write_json_atomic(sp, data)
        except OSError as ex:
            return False, f"Couldn't write {sp}: {ex}"
        return True, "Connection repaired. Limits appear after your next message in Claude Code."
    chain = cur.get("command") if isinstance(cur, dict) and cur.get("type") == "command" else None
    try:
        if not os.path.exists(_backup_path()):
            _write_json_atomic(_backup_path(), {"statusLine": cur})
        new = dict(cur) if isinstance(cur, dict) else {}
        new.update({"type": "command", "command": statusline_command(chain, config_dir)})
        data["statusLine"] = new
        os.makedirs(os.path.dirname(sp), exist_ok=True)
        _write_json_atomic(sp, data)
    except OSError as ex:
        return False, f"Couldn't write {sp}: {ex}"
    return True, "Connected. Limits appear after your next message in Claude Code." + (
        " Your existing status line keeps working." if chain else "")


def uninstall_statusline():
    sp = claude_settings_path()
    try:
        with open(sp, encoding="utf-8") as fh:
            data = json.load(fh)
        with open(_backup_path(), encoding="utf-8") as fh:
            old = json.load(fh).get("statusLine")
    except (OSError, ValueError):
        return False, "Nothing to restore."
    if not isinstance(data, dict):
        return False, "Settings file isn't a JSON object."
    if old is None:
        data.pop("statusLine", None)
    else:
        data["statusLine"] = old
    try:
        _write_json_atomic(sp, data)
        os.remove(_backup_path())
    except OSError as ex:
        return False, str(ex)
    return True, "Restored your previous status line."


def statusline_connected():
    try:
        with open(claude_settings_path(), encoding="utf-8") as fh:
            cmd = (json.load(fh).get("statusLine") or {}).get("command", "")
        return "--statusline" in str(cmd)
    except (OSError, ValueError, AttributeError):
        return False


def read_bridge(now=None):
    """-> (items, written_at) from the status-line file, or None. Expired windows are dropped."""
    now = now or time.time()
    try:
        with open(live_file_path(), encoding="utf-8") as fh:
            d = json.load(fh)
        rl, ts = d["rate_limits"], float(d["ts"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    items = []
    if isinstance(rl, dict):
        for key in ("five_hour", "seven_day"):
            w = rl.get(key)
            if not isinstance(w, dict) or not isinstance(w.get("used_percentage"), (int, float)):
                continue
            rs = w.get("resets_at")
            rs = float(rs) if isinstance(rs, (int, float)) and not isinstance(rs, bool) else None
            if rs is not None and rs <= now:
                continue            # that window has ended; Claude Code drops it too
            items.append({"key": key, "label": LIVE_LABELS[key], "pct": float(w["used_percentage"]), "resets": rs})
    return items, ts


def read_credentials():
    paths = []
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        paths += [os.path.join(p.strip(), ".credentials.json") for p in env.split(",") if p.strip()]
    else:
        paths += [os.path.join(HOME, ".claude", ".credentials.json"),
                  os.path.join(HOME, ".config", "claude", ".credentials.json")]
    for p in paths:
        try:
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and isinstance(data.get("claudeAiOauth"), dict):
                return data["claudeAiOauth"]
        except (OSError, ValueError):
            continue
    if IS_MAC:  # Claude Code keeps the login in the macOS Keychain
        try:
            r = subprocess.run(["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
                               capture_output=True, text=True, timeout=8)
            if r.returncode == 0:
                data = json.loads(r.stdout.strip())
                if isinstance(data, dict) and isinstance(data.get("claudeAiOauth"), dict):
                    return data["claudeAiOauth"]
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return None


def plan_label(sub, tier):
    if not sub:
        return None
    label = str(sub).replace("_", " ").title()
    m = re.search(r"(\d+)x", str(tier or ""))
    return f"{label} {m.group(1)}x" if m else label


def parse_live(js):
    items = []
    if not isinstance(js, dict):
        return items, None
    for k, v in js.items():
        if isinstance(v, dict) and isinstance(v.get("utilization"), (int, float)):
            items.append({"key": k, "label": LIVE_LABELS.get(k, k.replace("_", " ").capitalize()),
                          "pct": float(v["utilization"]), "resets": parse_ts(v.get("resets_at"))})
    items.sort(key=lambda it: LIVE_ORDER.index(it["key"]) if it["key"] in LIVE_ORDER else 99)
    extra = None
    ex = js.get("extra_usage")
    if isinstance(ex, dict) and ex.get("is_enabled"):
        lim, used = ex.get("monthly_limit"), ex.get("used_credits")
        ok = isinstance(lim, (int, float)) and lim > 0 and isinstance(used, (int, float))
        extra = {"pct": used / lim * 100.0 if ok else None}
    return items, extra


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """The login token must only ever go to the address we chose, so never follow a redirect."""

    def redirect_request(self, *a, **k):
        return None


def http_get_json(url, headers, timeout=10):
    opener = urllib.request.build_opener(_NoRedirect)
    with opener.open(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class LiveLimits:
    def __init__(self, app):
        self.app = app
        self.state = {"status": "idle"}
        self.lock = threading.Lock()
        self.wake = threading.Event()

    def get(self):
        with self.lock:
            return dict(self.state)

    def fetch(self):
        """Official status-line data first; the saved login is used only if the user opted in."""
        b = read_bridge()
        if b and b[0]:
            age = time.time() - b[1]
            st = {"status": "ok" if age <= 900 else "stale", "plan": None, "items": b[0], "extra": None,
                  "fetched": b[1], "source": "statusline"}
            if st["status"] == "stale":
                st["msg"] = "Claude Code reports these while it is open."
            return st
        if not self.app.cfg.get("live_oauth"):
            if b is not None:
                return {"status": "wait", "msg": "Waiting for Claude Code to report your limits (after your next message)."}
            return {"status": "nobridge",
                    "msg": "Not connected yet. One click, no login access needed:"}
        return self.fetch_oauth()

    def fetch_oauth(self):
        oauth = read_credentials()
        if not oauth or not oauth.get("accessToken"):
            return {"status": "nologin", "msg": "No Claude Code login found on this computer."}
        plan = plan_label(oauth.get("subscriptionType"), oauth.get("rateLimitTier"))
        exp = oauth.get("expiresAt")
        if isinstance(exp, (int, float)) and exp / 1000.0 < time.time():
            return {"status": "expired", "plan": plan,
                    "msg": "Saved login has expired. Open Claude Code once to refresh it."}
        try:
            js = http_get_json(USAGE_URL, {
                "Authorization": "Bearer " + str(oauth["accessToken"]),
                "anthropic-beta": "oauth-2025-04-20",
                "Accept": "application/json",
                "User-Agent": f"limitline/{VERSION}",
            })
        except urllib.error.HTTPError as ex:
            if ex.code in (401, 403):
                return {"status": "auth", "plan": plan,
                        "msg": f"Plan limits aren't available for this login (HTTP {ex.code})."}
            if ex.code == 429:
                return {"status": "rate", "plan": plan, "msg": "Rate-limited; will retry in a few minutes."}
            return {"status": "error", "plan": plan, "msg": f"Anthropic returned HTTP {ex.code}."}
        except Exception:  # noqa: BLE001 - offline, DNS, TLS, bad JSON ...
            return {"status": "offline", "plan": plan, "msg": "Couldn't reach Anthropic - showing local data."}
        items, extra = parse_live(js)
        if not items:
            return {"status": "error", "plan": plan, "msg": "No limit data in the response."}
        return {"status": "ok", "plan": plan, "items": items, "extra": extra, "fetched": time.time()}

    def loop(self):
        while True:
            cfg = self.app.cfg
            interval = max(30, int(cfg.get("live_interval_sec", 120)))
            if cfg.get("live_limits", True) and not self.app.args.no_live:
                st = self.fetch()
                with self.lock:
                    prev = self.state
                    if (st["status"] != "ok" and prev.get("items")
                            and time.time() - prev.get("fetched", 0) < 900):
                        st = dict(prev, status="stale", msg=st.get("msg"))
                    self.state = st
                if st["status"] == "rate":
                    interval = max(interval, 300)
            else:
                with self.lock:
                    self.state = {"status": "off"}
            self.app.worker.wake.set()
            # adaptive: faster while you're actively using Claude, slower when idle,
            # and always re-check right after a limit resets
            snap = self.app.snap or {}
            last = snap.get("last_ts")
            now = time.time()
            if last and now - last < 600:
                interval = min(interval, 60)
            elif not last or now - last > 3600:
                interval = max(interval, 300)
            resets = [it["resets"] for it in (self.state.get("items") or []) if it.get("resets") and it["resets"] > now]
            if resets:
                interval = min(interval, max(5, min(resets) - now + 5))
            if self.state.get("source") == "statusline" or self.state.get("status") in ("nobridge", "wait"):
                interval = min(interval, 10)    # the file is local and tiny: pick up changes quickly
            self.wake.wait(interval)
            self.wake.clear()


class DemoLive:
    def __init__(self, mode):
        self.mode = mode
        self.wake = threading.Event()

    def get(self):
        if self.mode == "local":
            return {"status": "off"}
        now = time.time()
        reset5 = math.floor(now / 3600) * 3600 + 3600 * 2 + 1800
        today = local_day(now)
        monday = today + (7 - date.fromordinal(today).weekday()) % 7 or today + 7
        reset7 = day_start(monday) + 9 * 3600
        return {"status": "ok", "plan": None, "fetched": now - 40, "extra": None, "items": [
            {"key": "five_hour", "label": LIVE_LABELS["five_hour"], "pct": 64.0, "resets": reset5},
            {"key": "seven_day", "label": LIVE_LABELS["seven_day"], "pct": 38.0, "resets": reset7},
        ]}

    def loop(self):
        return


# =============================================================================
# Alert rules (pure functions, no UI)
# =============================================================================
def alert_levels_for(cfg, scope):
    base = cfg.get("alert_levels") if scope == "session" else cfg.get("alert_levels_week")
    levels = set()
    for x in base or []:
        if isinstance(x, int) and not isinstance(x, bool) and 0 < x <= 100:
            levels.add(x)
    step = cfg.get("alert_step") or 0
    if isinstance(step, int) and step >= 5:
        levels.update(range(step, 101, step))
    return sorted(levels)


def _hhmm(text):
    h, m = str(text).strip().split(":")
    return int(h) * 60 + int(m)


def alerts_quiet(cfg, now):
    """True while alerts should stay silent (snoozed, or inside quiet hours). The banner still shows."""
    if float(cfg.get("snooze_until") or 0) > now:
        return True
    if not cfg.get("quiet_enabled"):
        return False
    try:
        a, b = _hhmm(cfg.get("quiet_from", "22:00")), _hhmm(cfg.get("quiet_to", "08:00"))
    except ValueError:
        return False
    lt = time.localtime(now)
    cur = lt.tm_hour * 60 + lt.tm_min
    if a == b:
        return False
    return a <= cur < b if a < b else (cur >= a or cur < b)


def plan_alerts(cfg, s, alerted, now):
    """-> list of new alert events; marks them in `alerted` so each fires once per window/period."""
    events = []
    if not cfg.get("alerts") or not s:
        return events
    w, g = s["window"], s["gauge"]
    pace_only = cfg.get("alerts_pace_only")
    checks = []   # (key, scope, pct, label, reset, elapsed)
    if w and g["pct"] is not None:
        checks.append(("w%d" % int(w["end"]), "session", g["pct"], "Your 5-hour window", w["end"], w["elapsed"]))
    if s["live"].get("status") in ("ok", "stale"):
        for it in s["live"].get("items") or []:
            if it["key"] == "five_hour":
                continue
            rs = it["resets"]
            el = min(1.0, max(0.0, 1 - ((rs or now) - now) / (7 * 86400.0)))
            checks.append(("%s:%d" % (it["key"], int(rs or 0)), "week", it["pct"], it["label"], rs, el))
    for key, scope, pct, label, reset, elapsed in checks:
        levels = alert_levels_for(cfg, scope)
        if not levels or (pace_only and not pct / 100.0 > elapsed):
            continue
        done = set(alerted.get(key, []))
        hit = [lv for lv in levels if pct >= lv and lv not in done]
        if hit:
            alerted[key] = sorted(done | set(hit))
            tail = f" · resets {fmt_when(reset, now)}" if reset else ""
            events.append({"kind": "threshold", "scope": scope, "level": max(hit), "pct": pct, "label": label,
                           "text": f"{label} is at {pct:.0f}%{tail}", "title": f"Limitline · {max(hit)}%"})
    # forecast: you will run out before the window resets, and you've really started using it
    eta = g.get("eta")
    if cfg.get("alert_forecast") and w and eta and g["pct"] is not None and 20 <= g["pct"] < 100 \
            and w.get("rate", 0) > 0 and eta < w["end"]:
        fkey = "f:w%d" % int(w["end"])
        if not alerted.get(fkey):
            alerted[fkey] = [1]
            events.append({"kind": "forecast", "scope": "session", "level": 85, "pct": g["pct"],
                           "label": "5-hour window",
                           "text": f"At this pace you'll hit your limit around {fmt_clock(eta)}, "
                                   f"{fmt_dur(max(0, w['end'] - eta))} before it resets.",
                           "title": "Limitline · pace warning"})
    while len(alerted) > 60:
        alerted.pop(next(iter(alerted)))
    return events


# =============================================================================
# Aggregation
# =============================================================================
def new_agg():
    return [0, 0, 0, 0, 0.0, 0]  # input, output, cache write, cache read, cost, messages


def add(agg, e):
    agg[0] += e.inp
    agg[1] += e.out
    agg[2] += e.cw
    agg[3] += e.cr
    agg[4] += e.cost
    agg[5] += 1


def tok(agg):
    return agg[0] + agg[1] + agg[2] + agg[3]


def mval(agg, metric):
    if metric == "cost":
        return agg[4]
    if metric == "io":
        return agg[0] + agg[1]
    return tok(agg)


def eval_entry(e, metric):
    if metric == "cost":
        return e.cost
    if metric == "io":
        return e.inp + e.out
    return e.inp + e.out + e.cw + e.cr


def ranked(groups, metric):
    rows = [{"fam": k[0], "name": k[1], "agg": a, "val": mval(a, metric)} for k, a in groups.items()]
    rows.sort(key=lambda r: -r["val"])
    return rows


def build_snapshot(entries, now, cfg, live, scan):
    metric = cfg.get("metric", "cost")
    today = local_day(now)
    live = live or {}
    snap = {"now": now, "metric": metric, "today": today, "scan": scan, "live": live,
            "has_data": bool(entries), "last_ts": entries[-1].ts if entries else None}

    # ---- 5-hour windows, same rule Claude Code uses: start at the hour of the first message
    blocks, cur = [], None
    for e in entries:
        if cur is None or e.ts >= cur["end"] or e.ts - cur["last"] >= WINDOW_SEC:
            st = (e.ts // 3600) * 3600
            cur = {"start": st, "end": st + WINDOW_SEC, "first": e.ts, "last": e.ts, "agg": new_agg()}
            blocks.append(cur)
        cur["last"] = e.ts
        add(cur["agg"], e)
    active = blocks[-1] if blocks and now < blocks[-1]["end"] else None
    for b in blocks:
        b["val"] = mval(b["agg"], metric)
    record = max((b["val"] for b in blocks if b is not active), default=0.0)
    custom = float(cfg.get("limit_value") or 0) if cfg.get("limit_mode") == "custom" else 0.0
    limit = custom if custom > 0 else (record if record > 0 else None)
    snap.update(record=record, limit=limit, limit_src="custom" if custom > 0 else ("auto" if record > 0 else None))

    # ---- current window (prefer the live reset time - it's authoritative)
    items = {}
    if live.get("status") in ("ok", "stale"):
        items = {it["key"]: it for it in live.get("items") or []}
    five = items.get("five_hour")
    wstart = wend = src = None
    if five and five.get("resets") and five["resets"] > now:
        wend, src = five["resets"], "live"
        wstart = wend - WINDOW_SEC
    elif active:
        wstart, wend, src = active["start"], active["end"], "local"
    window = None
    if wstart is not None:
        wagg, recent, models, last = new_agg(), new_agg(), {}, None
        burn_from = max(wstart, now - 1800)
        for e in reversed(entries):
            if e.ts < wstart:
                break
            if e.ts >= wend:
                continue
            add(wagg, e)
            add(models.setdefault((e.fam, e.disp), new_agg()), e)
            if last is None:
                last = e.ts
            if e.ts >= burn_from:
                add(recent, e)
        span = max(60.0, now - burn_from) / 60.0
        rate = mval(recent, metric) / span
        remaining = max(0.0, wend - now)
        val = mval(wagg, metric)
        window = {"start": wstart, "end": wend, "src": src, "agg": wagg, "val": val, "last": last,
                  "rate": rate, "rate_tokens": tok(recent) / span, "rate_cost_h": recent[4] / span * 60,
                  "proj": val + rate * remaining / 60.0, "remaining": remaining,
                  "elapsed": min(1.0, max(0.0, (now - wstart) / WINDOW_SEC)),
                  "models": ranked(models, metric)}
    snap["window"] = window

    gauge = {"pct": None, "src": None, "proj_pct": None, "eta": None}
    if window:
        if src == "live":
            pct = float(five["pct"])
            gauge.update(pct=pct, src="live", proj_pct=pct)
            if window["val"] > 0 and pct > 0 and window["rate"] > 0:
                per = pct / window["val"]
                gauge["proj_pct"] = window["proj"] * per
                if pct < 100:
                    secs = (100 - pct) / (per * window["rate"]) * 60
                    if secs < window["remaining"]:
                        gauge["eta"] = now + secs
        elif limit:
            gauge.update(pct=window["val"] / limit * 100, src=snap["limit_src"],
                         proj_pct=window["proj"] / limit * 100)
            if window["rate"] > 0 and window["val"] < limit:
                secs = (limit - window["val"]) / window["rate"] * 60
                if secs < window["remaining"]:
                    gauge["eta"] = now + secs
    snap["gauge"] = gauge

    # ---- totals, charts, breakdowns
    k_today, k7, k30, kprev = new_agg(), new_agg(), new_agg(), new_agg()
    s_today, s7, s30 = set(), set(), set()
    hour0 = hour_start(now) - 23 * 3600
    hourly = [{"start": hour0 + i * 3600, "fam": defaultdict(float), "agg": new_agg()} for i in range(24)]
    daily = [{"day": today - 29 + i, "fam": defaultdict(float), "agg": new_agg()} for i in range(30)]
    heat = [[0.0] * 24 for _ in range(7)]
    heat_n = [[0] * 24 for _ in range(7)]
    projs = {"today": {}, "7d": {}, "30d": {}}
    sessions, daily_models, models_today = {}, {}, {}

    def proj_add(bucket, e, v):
        p = bucket.get(e.project)
        if p is None:
            p = bucket[e.project] = {"name": e.project, "agg": new_agg(), "val": 0.0, "sess": set(), "last": 0.0}
        add(p["agg"], e)
        p["val"] += v
        p["sess"].add(e.session)
        p["last"] = max(p["last"], e.ts)

    for e in entries:
        v = eval_entry(e, metric)
        dd = today - e.day
        add(daily_models.setdefault((e.day, e.model), new_agg()), e)
        s = sessions.get(e.session)
        if s is None:
            s = sessions[e.session] = {"id": e.session, "project": e.project, "first": e.ts, "last": e.ts,
                                       "agg": new_agg(), "models": defaultdict(float)}
        s["last"] = e.ts
        add(s["agg"], e)
        s["models"][(e.fam, e.disp)] += v
        if e.ts >= hour0:
            i = int((e.ts - hour0) // 3600)
            if 0 <= i < 24:
                hourly[i]["fam"][e.fam] += v
                add(hourly[i]["agg"], e)
        if 0 <= dd < 30:
            b = daily[29 - dd]
            b["fam"][e.fam] += v
            add(b["agg"], e)
            heat[e.wday][e.hour] += v
            heat_n[e.wday][e.hour] += 1
            add(k30, e)
            s30.add(e.session)
            proj_add(projs["30d"], e, v)
            if dd < 7:
                add(k7, e)
                s7.add(e.session)
                proj_add(projs["7d"], e, v)
            if dd == 0:
                add(k_today, e)
                s_today.add(e.session)
                proj_add(projs["today"], e, v)
                add(models_today.setdefault((e.fam, e.disp), new_agg()), e)
            if 1 <= dd <= 7:
                add(kprev, e)

    snap["kpi"] = {"today": {"agg": k_today, "sess": len(s_today)}, "7d": {"agg": k7, "sess": len(s7)},
                   "30d": {"agg": k30, "sess": len(s30)}, "avg_prev7": mval(kprev, metric) / 7.0}
    for b in hourly + daily:
        b["fam"] = dict(b["fam"])
    snap["hourly"], snap["daily"] = hourly, daily
    snap["heat"], snap["heat_n"] = heat, heat_n
    snap["heat_max"] = max(max(r) for r in heat)
    snap["models_today"] = ranked(models_today, metric)
    snap["projects"] = {}
    for rng_key, bucket in projs.items():
        rows = []
        for p in bucket.values():
            p["sess"] = len(p["sess"])
            rows.append(p)
        rows.sort(key=lambda r: -r["val"])
        snap["projects"][rng_key] = rows
    sess = sorted(sessions.values(), key=lambda x: -x["last"])[:15]
    for x in sess:
        x["val"] = mval(x["agg"], metric)
        top = max(x["models"].items(), key=lambda kv: kv[1]) if x["models"] else (("other", "?"), 0)
        x["fam"], x["model"] = top[0]
        x["live"] = now - x["last"] < 15 * 60
        x["n_models"] = len(x["models"])
        del x["models"]
    snap["sessions"] = sess
    snap["n_sessions"] = len(sessions)
    # how much of Claude Code's own billed total the logs capture (logs miss some input/background calls)
    cs = scan.get("cost_states") or {}
    logged = billed = 0.0
    for sid in sessions:
        if sid in cs and cs[sid][0] > 0:
            billed += cs[sid][0]
            logged += cs[sid][1]
    for x in sess:
        st = cs.get(x["id"])
        # only show Claude Code's figure when its snapshot is up to date with the log
        x["cc_cost"] = st[0] if st and x["agg"][4] <= st[1] * 1.03 + 0.01 else None
    snap["coverage"] = (logged / billed) if billed > 0 else None
    snap["unpriced"] = dict(scan.get("unpriced") or {})
    shown = blocks[-6:][::-1]
    for b in shown:
        b["active"] = b is active
        b["is_record"] = b is not active and record > 0 and b["val"] >= record
    snap["blocks"] = shown
    snap["daily_models"] = daily_models
    return snap


# =============================================================================
# Platform helpers
# =============================================================================
def notify_desktop(title, message):
    try:
        if IS_MAC:
            script = f"display notification {json.dumps(message)} with title {json.dumps(title)}"
            subprocess.Popen(["osascript", "-e", script])
        elif IS_WIN:
            t, m = title.replace("'", "''"), message.replace("'", "''")
            ps = ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
                  "ContentType = WindowsRuntime] | Out-Null;"
                  "$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
                  "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
                  "$t=$x.GetElementsByTagName('text');"
                  f"$t.Item(0).AppendChild($x.CreateTextNode('{t}')) | Out-Null;"
                  f"$t.Item(1).AppendChild($x.CreateTextNode('{m}')) | Out-Null;"
                  "$n=[Windows.UI.Notifications.ToastNotification]::new($x);"
                  "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
                  "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show($n)")
            subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                              "-Command", ps], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            subprocess.Popen(["notify-send", "-a", APP_NAME, title, message],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, ValueError):
        pass


def open_path(p):
    try:
        if IS_WIN:
            os.startfile(p)  # type: ignore[attr-defined]
        elif IS_MAC:
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def autostart_path():
    if IS_WIN:
        return os.path.join(os.environ.get("APPDATA", HOME), "Microsoft", "Windows", "Start Menu",
                            "Programs", "Startup", "Limitline.vbs")
    if IS_MAC:
        return os.path.join(HOME, "Library", "LaunchAgents", "com.limitline.plist")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config")
    return os.path.join(base, "autostart", "limitline.desktop")


def autostart_enabled():
    return os.path.exists(autostart_path())


def set_autostart(on):
    p, script, py = autostart_path(), os.path.abspath(__file__), sys.executable
    try:
        if not on:
            if os.path.exists(p):
                os.remove(p)
            return True
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if IS_WIN:
            pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
            py = pyw if os.path.exists(pyw) else py
            content = f'CreateObject("WScript.Shell").Run """{py}"" ""{script}""", 0, False\r\n'
        elif IS_MAC:
            content = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                       '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                       '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict>'
                       '<key>Label</key><string>com.limitline</string>'
                       f'<key>ProgramArguments</key><array><string>{py}</string><string>{script}</string></array>'
                       '<key>RunAtLoad</key><true/></dict></plist>\n')
        else:
            content = (f"[Desktop Entry]\nType=Application\nName={APP_NAME}\n"
                       f'Exec="{py}" "{script}"\nX-GNOME-Autostart-enabled=true\n')
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(content)
        return True
    except OSError:
        return False


# =============================================================================
# UI - theme
# =============================================================================
THEMES = {
    "dark": {
        "bg": "#0e0e0d", "surface": "#161614", "raised": "#1f1e1b", "border": "#2a2925",
        "ink": "#f3f0e8", "ink2": "#c8c4b8", "muted": "#8b877c", "grid": "#252420", "base": "#3a3934",
        "hover": "#22211e", "seg_bg": "#11110f", "seg_sel": "#2f2e29",
        "series": {"opus": "#3987e5", "sonnet": "#d95926", "haiku": "#199e70", "fable": "#c98500",
                   "other": "#77756f"},
        "heat": ["#17345a", "#1c5cab", "#2a78d6", "#5598e7", "#9ec5f4"],
    },
    "light": {
        "bg": "#ece9e1", "surface": "#fbfaf7", "raised": "#f4f2ec", "border": "#dedbd0",
        "ink": "#14130f", "ink2": "#4f4d46", "muted": "#6f6c63", "grid": "#ebe8df", "base": "#c4c0b3",
        "hover": "#efede6", "seg_bg": "#ebe8e0", "seg_sel": "#ffffff",
        "series": {"opus": "#2a78d6", "sonnet": "#eb6834", "haiku": "#1baf7a", "fable": "#eda100",
                   "other": "#a3a29c"},
        "heat": ["#d7e7fb", "#9ec5f4", "#5598e7", "#256abf", "#104281"],
    },
}
ACCENTS = {"gold": ("#d3b787", "#94702f"), "claude": ("#d97757", "#c2603d"), "ocean": ("#4c9df0", "#1f6fd1"),
           "forest": ("#3fae7a", "#1d8556"), "violet": ("#9085e9", "#5b4bc4")}
STATUS = {"good": "#0ca30c", "warn": "#fab219", "crit": "#d03b3b"}


def make_theme(name, accent):
    th = dict(THEMES.get(name, THEMES["dark"]))
    pair = ACCENTS.get(accent, ACCENTS["gold"])
    th["accent"] = pair[0] if name == "dark" else pair[1]
    th["accent_soft"] = mix(th["surface"], th["accent"], 0.18)
    th["name"] = name
    return th


def severity(pct, th):
    """-> (key, colour, label, shape). Shape keeps state readable without colour."""
    if pct is None:
        return ("idle", th["muted"], "Idle", "ring")
    if pct >= 100:
        return ("crit", STATUS["crit"], "At limit", "square")
    if pct >= 90:
        return ("crit", STATUS["crit"], "Near limit", "square")
    if pct >= 70:
        return ("warn", STATUS["warn"], "Heavy use", "triangle")
    return ("ok", th["accent"], "On track", "dot")


def outlook(g, w, th):
    """Status chip for the current window: where you are *and* where you're heading."""
    if not w:
        return severity(None, th)
    pct = g["pct"]
    if pct is None:
        return ("idle", th["muted"], "No limit yet", "ring")
    if pct >= 90:
        return severity(pct, th)
    if g["eta"]:
        return ("warn", STATUS["warn"], f"Limit by {fmt_clock(g['eta'])}", "triangle")
    return severity(pct, th)


def detect_scale(root):
    if IS_MAC:
        return 1.0
    try:
        dpi = float(root.winfo_fpixels("1i"))
    except tk.TclError:
        dpi = 96.0
    return max(1.0, min(3.0, round(dpi / 96.0 * 4) / 4))


def make_fonts(root):
    fams = set(tkfont.families(root))

    def pick(*names):
        return next((n for n in names if n in fams), None)

    sans = pick("Segoe UI", "SF Pro Text", "Helvetica Neue", "Inter", "Cantarell", "Ubuntu", "Noto Sans",
                "DejaVu Sans", "Helvetica", "Arial") or tkfont.nametofont("TkDefaultFont").actual("family")
    semi = pick("Segoe UI Semibold", "SF Pro Text Semibold", "Inter SemiBold", "Inter Semi Bold",
                "Noto Sans SemiBold")
    light = pick("Segoe UI Light", "Segoe UI Semilight", "SF Pro Display Light", "Helvetica Neue Light",
                 "Inter Light", "Inter Thin", "Noto Sans Light", "Roboto Light", "Ubuntu Light", "Cantarell Light")
    k = 1.3 if IS_MAC else 1.0

    def F(size, weight="normal"):
        size = int(round(size * k))
        if weight == "semi" and semi:
            return tkfont.Font(root=root, family=semi, size=size)
        return tkfont.Font(root=root, family=sans, size=size, weight="bold" if weight != "normal" else "normal")

    hero = (tkfont.Font(root=root, family=light, size=int(round(23 * k))) if light else F(20, "semi"))
    return {"hero": hero, "h1": F(16, "semi"), "h2": F(12, "semi"), "title": F(10, "semi"),
            "body": F(10), "bodyb": F(10, "semi"), "small": F(9), "smallb": F(9, "semi"),
            "tiny": F(8), "tinyb": F(8, "semi"), "label": F(8, "semi")}


def ring_data(size, rings, bg):
    """Anti-aliased ring gauge as Tk PhotoImage data (pure Python, cached by caller)."""
    cx = cy = size / 2.0
    two_pi = 2 * math.pi
    bgc = _rgb(bg)
    prep = []
    for r in rings:
        sweep = max(0.0, min(1.0, r["frac"])) * two_pi
        caps = []
        if 0 < sweep < two_pi - 1e-6:
            caps = [(0.0, -r["R"]), (r["R"] * math.sin(sweep), -r["R"] * math.cos(sweep))]
        prep.append((r["R"], r["h"], sweep, caps, _rgb(r["track"]), _rgb(r["fill"])))
    sqrt, atan2 = math.sqrt, math.atan2
    rows = []
    for py in range(size):
        y = py + 0.5 - cy
        row = []
        for px_ in range(size):
            x = px_ + 0.5 - cx
            d = sqrt(x * x + y * y)
            c0, c1, c2 = bgc
            for R, h, sweep, caps, tc, fc in prep:
                ra = h - abs(d - R) + 0.5
                if ra <= 0:
                    continue
                if ra > 1:
                    ra = 1.0
                c0 += (tc[0] - c0) * ra
                c1 += (tc[1] - c1) * ra
                c2 += (tc[2] - c2) * ra
                if sweep <= 0:
                    continue
                if not caps:
                    fa = ra
                else:
                    ang = atan2(x, -y)
                    if ang < 0:
                        ang += two_pi
                    fa = ra if ang <= sweep else 0.0
                    for qx, qy in caps:
                        dc = h - sqrt((x - qx) ** 2 + (y - qy) ** 2) + 0.5
                        if dc > fa:
                            fa = 1.0 if dc > 1 else dc
                if fa > 0:
                    c0 += (fc[0] - c0) * fa
                    c1 += (fc[1] - c1) * fa
                    c2 += (fc[2] - c2) * fa
            row.append("#%02x%02x%02x" % (int(c0 + 0.5), int(c1 + 0.5), int(c2 + 0.5)))
        rows.append("{" + " ".join(row) + "}")
    return " ".join(rows)


def top_rounded(c, x0, y0, x1, y1, r, **kw):
    """Bar with rounded data-end and a square baseline."""
    r = max(0.0, min(r, (x1 - x0) / 2.0, (y1 - y0)))
    if r < 1.5:
        return c.create_rectangle(x0, y0, x1, y1, width=0, **kw)
    pts = [x0 + r, y0, x0 + r, y0, x1 - r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y0 + r,
           x1, y1, x1, y1, x1, y1, x0, y1, x0, y1, x0, y1, x0, y0 + r, x0, y0 + r, x0, y0]
    return c.create_polygon(pts, smooth=True, splinesteps=8, width=0, **kw)

# =============================================================================
# Anti-aliased vector rasteriser (pure Python, cached) - used for icons, bars,
# toggles, pills and rounded corners so nothing on screen is pixel-jagged.
# =============================================================================
def _lum(h):
    r, g, b = _rgb(h)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def _acov(d):
    c = 0.5 - d
    return 0.0 if c <= 0.0 else (1.0 if c >= 1.0 else c)


def _dseg(x, y, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / ll))
    qx, qy = ax + t * dx - x, ay + t * dy - y
    return math.sqrt(qx * qx + qy * qy)


def g_line(pts, hw, color):
    """Round-capped, round-joined polyline stroke of half-width hw."""
    segs = [(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) for i in range(len(pts) - 1)]
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    bb = (min(xs) - hw - 1, min(ys) - hw - 1, max(xs) + hw + 1, max(ys) + hw + 1)
    return bb, (lambda x, y: _acov(min(_dseg(x, y, *sg) for sg in segs) - hw)), color


def g_disc(cx, cy, r, color):
    return (cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1), \
        (lambda x, y: _acov(math.hypot(x - cx, y - cy) - r)), color


def g_ring(cx, cy, r, hw, color):
    return (cx - r - hw - 1, cy - r - hw - 1, cx + r + hw + 1, cy + r + hw + 1), \
        (lambda x, y: _acov(abs(math.hypot(x - cx, y - cy) - r) - hw)), color


def g_rrect(x0, y0, x1, y1, r, color, hw=None):
    """Filled (or outlined, when hw is given) rounded rectangle."""
    hx, hy = (x1 - x0) / 2.0, (y1 - y0) / 2.0
    cx, cy = x0 + hx, y0 + hy
    r = max(0.0, min(r, hx, hy))

    def sd(x, y):
        qx, qy = abs(x - cx) - hx + r, abs(y - cy) - hy + r
        return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r

    fn = (lambda x, y: _acov(sd(x, y))) if hw is None else (lambda x, y: _acov(abs(sd(x, y)) - hw))
    return (x0 - 1, y0 - 1, x1 + 1, y1 + 1), fn, color


def g_rect(x0, y0, x1, y1, color):
    def fn(x, y):
        ox = min(x + 0.5, x1) - max(x - 0.5, x0)
        oy = min(y + 0.5, y1) - max(y - 0.5, y0)
        return ox * oy if ox > 0 and oy > 0 else 0.0
    return (x0 - 1, y0 - 1, x1 + 1, y1 + 1), fn, color


def g_poly(pts, color, grow=0.0):
    """Filled polygon; grow > 0 rounds the corners (pass a slightly inset polygon)."""
    edges = [(pts[i][0], pts[i][1], pts[(i + 1) % len(pts)][0], pts[(i + 1) % len(pts)][1]) for i in range(len(pts))]
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]

    def fn(x, y):
        d = min(_dseg(x, y, *e) for e in edges)
        inside = False
        for ax, ay, bx, by in edges:
            if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
                inside = not inside
        return _acov((-d if inside else d) - grow)
    return (min(xs) - grow - 1, min(ys) - grow - 1, max(xs) + grow + 1, max(ys) + grow + 1), fn, color


def render_gfx(w, h, bg, shapes):
    """Composite shapes over a flat background -> Tk PhotoImage data."""
    bgc = _rgb(bg)
    prep = [(bb, fn, _rgb(col)) for bb, fn, col in shapes]
    rows = []
    for py in range(h):
        y = py + 0.5
        row = []
        for pxi in range(w):
            x = pxi + 0.5
            c0, c1, c2 = bgc
            for (bx0, by0, bx1, by1), fn, col in prep:
                if x < bx0 or x > bx1 or y < by0 or y > by1:
                    continue
                a = fn(x, y)
                if a > 0.0:
                    c0 += (col[0] - c0) * a
                    c1 += (col[1] - c1) * a
                    c2 += (col[2] - c2) * a
            row.append("#%02x%02x%02x" % (int(c0 + 0.5), int(c1 + 0.5), int(c2 + 0.5)))
        rows.append("{" + " ".join(row) + "}")
    return " ".join(rows)


# =============================================================================
# Mascot "Tick": an original little gauge character that reacts to alerts
# =============================================================================
MASCOT_N = 12


def mascot_mood(ev):
    if ev["kind"] == "reset":
        return "joy"
    if ev["kind"] == "forecast":
        return "worried"
    p = ev["pct"]
    return "happy" if p < 50 else "calm" if p < 75 else "worried" if p < 90 else "alarmed" if p < 100 else "out"


def mascot_caption(ev):
    m = mascot_mood(ev)
    if ev["kind"] == "forecast":
        return ev["text"]
    return {"happy": "Nice and easy. %d%% used." % ev["pct"], "calm": "Halfway there. %d%% used." % ev["pct"],
            "worried": "Heads up: %d%% used." % ev["pct"], "alarmed": "Almost out! %d%% used." % ev["pct"],
            "out": "Limit reached.", "joy": "Fresh start! Window reset."}[m]


def mascot_shapes(i, mood, body, ink, size):
    """Shapes for frame i of MASCOT_N, on a 100x100 design grid scaled to `size`."""
    k = size / 100.0
    ph = 2 * math.pi * i / MASCOT_N
    bob = math.sin(ph) * 2.5 if mood not in ("out",) else 0
    if mood == "alarmed":
        bob = math.sin(ph * 2) * 2.0
    tilt = {"happy": -0.5, "calm": -0.1, "worried": 0.35, "alarmed": 0.7, "out": 1.0, "joy": -0.7}[mood]
    top = 30 + bob
    sh = []
    sh.append(g_rrect(24, top, 76, top + 50, 16, body))
    sh.append(g_rrect(30, top + 6, 70, top + 30, 10, "#ffffff"))
    ax, ay = 50, top
    tipx, tipy = ax + math.sin(tilt + math.sin(ph) * 0.12) * 20, ay - math.cos(tilt) * 20
    sh.append(g_line([(ax, ay), (tipx, tipy)], 1.6, ink))
    sh.append(g_disc(tipx, tipy, 3.6, body if mood != "out" else "#d03b3b"))
    blink = i in (5, 6) and mood in ("happy", "calm", "worried")
    ey = top + 17
    if mood == "joy":
        for ex in (41, 59):
            sh.append(g_line([(ex - 4, ey + 2), (ex, ey - 3), (ex + 4, ey + 2)], 1.6, ink))
    elif mood == "out":
        for ex in (41, 59):
            sh.append(g_line([(ex - 3.5, ey - 3.5), (ex + 3.5, ey + 3.5)], 1.5, ink))
            sh.append(g_line([(ex - 3.5, ey + 3.5), (ex + 3.5, ey - 3.5)], 1.5, ink))
    elif blink:
        for ex in (41, 59):
            sh.append(g_line([(ex - 3.5, ey), (ex + 3.5, ey)], 1.5, ink))
    else:
        r = 4.6 if mood == "alarmed" else 3.6
        for ex in (41, 59):
            sh.append(g_disc(ex, ey, r, ink))
    my = top + 41
    if mood in ("happy", "joy"):
        sh.append(g_line([(41, my - 5), (50, my + 1), (59, my - 5)], 1.8, "#ffffff"))
    elif mood == "calm":
        sh.append(g_line([(43, my - 3), (57, my - 3)], 1.8, "#ffffff"))
    elif mood == "worried":
        sh.append(g_line([(42, my), (50, my - 3), (58, my)], 1.8, "#ffffff"))
        d = (i % MASCOT_N) / MASCOT_N
        sh.append(g_disc(70, top + 12 + d * 10, 3.2, "#7cc4f0"))
    elif mood == "alarmed":
        sh.append(g_ring(50, my - 1, 4.5, 1.4, "#ffffff"))
        sh.append(g_disc(72, top + 8 + (i % 6) * 2.5, 3.2, "#7cc4f0"))
    else:
        sh.append(g_line([(42, my + 1), (47, my - 2), (53, my + 1), (58, my - 2)], 1.8, "#ffffff"))
    if mood == "joy":
        for n, (sx, sy) in enumerate(((18, 28), (84, 36), (80, 14))):
            r = 2.2 + 1.8 * abs(math.sin(ph + n))
            sh.append(g_line([(sx - r, sy), (sx + r, sy)], 1.0, body))
            sh.append(g_line([(sx, sy - r), (sx, sy + r)], 1.0, body))
    # feet
    sh.append(g_disc(38, top + 53, 4.5, ink))
    sh.append(g_disc(62, top + 53, 4.5, ink))
    # arm wave for happy/joy
    if mood in ("happy", "joy"):
        wv = math.sin(ph * 2) * 6
        sh.append(g_line([(76, top + 30), (86, top + 20 + wv)], 2.4, body))
    sc = []
    for bb, fn, col in sh:
        x0, y0, x1, y1 = bb
        sc.append(((x0 * k, y0 * k, x1 * k, y1 * k),
                   (lambda x, y, fn=fn: fn(x / k, y / k)), col))
    return sc


class Mascot:
    """Borderless card with an animated character; frames are rendered off the UI thread."""

    def __init__(self, app):
        self.app, self.win, self.job = app, None, None
        self.frames, self.idx, self.token = [], 0, 0

    def wanted(self, ev):
        mode = self.app.cfg.get("mascot", "subtle")
        if mode == "off":
            return False
        if mode == "full":
            return True
        return ev["kind"] != "threshold" or ev["level"] >= 75

    def event(self, ev):
        if not self.wanted(ev):
            return
        self.token += 1
        tok, app = self.token, self.app
        mood = mascot_mood(ev)
        th = app.th
        body = {"happy": th["accent"], "calm": th["accent"], "joy": STATUS["good"],
                "worried": STATUS["warn"], "alarmed": STATUS["crit"], "out": STATUS["crit"]}[mood]
        size = app.px(104)
        animate = bool(app.cfg.get("mascot_animate", True)) and not reduced_motion()
        card = th["surface"]
        ink = "#1a1a1a"
        frames_wanted = range(MASCOT_N) if animate else [3]

        def work():
            try:
                data = [render_gfx(size, size, card, mascot_shapes(i, mood, body, ink, size)) for i in frames_wanted]
                app.q.put(("mascot", tok, ev, data, size, animate))
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def show(self, tok, ev, data, size, animate):
        if tok != self.token:
            return
        self.hide()
        app, th = self.app, self.app.th
        self.frames = []
        for d in data:
            im = tk.PhotoImage(master=app.root, width=size, height=size)
            im.put(d)
            self.frames.append(im)
        w = self.win = tk.Toplevel(app.root)
        w.withdraw()
        w.overrideredirect(True)
        try:
            w.attributes("-topmost", True)
        except tk.TclError:
            pass
        edge = tk.Frame(w, bg=th["accent"], padx=1, pady=1)
        edge.pack()
        card = tk.Frame(edge, bg=th["surface"], padx=app.px(10), pady=app.px(8))
        card.pack()
        self.lab = tk.Label(card, image=self.frames[0], bg=th["surface"], bd=0)
        self.lab.pack(side="left")
        tk.Label(card, text=mascot_caption(ev), bg=th["surface"], fg=th["ink"], font=app.f["body"],
                 wraplength=app.px(190), justify="left").pack(side="left", padx=(app.px(10), app.px(4)))
        for wd in (w, edge, card, self.lab) + tuple(card.winfo_children()):
            wd.bind("<Button-1>", lambda e: self.hide())
        w.update_idletasks()
        self.place(w)
        try:
            w.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        w.deiconify()
        w.lift()
        self.idx = 0
        self.t0 = time.time()
        self.life = 9.0 if self.app.cfg.get("mascot") == "full" else 6.5
        self.tick(animate)

    def place(self, w):
        r = self.app.root
        ww, wh = w.winfo_reqwidth(), w.winfo_reqheight()
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        x = r.winfo_rootx() - ww - self.app.px(10)
        if x < 8:
            x = r.winfo_rootx() + r.winfo_width() + self.app.px(10)
        x = max(8, min(x, sw - ww - 8))
        y = max(8, min(r.winfo_rooty(), sh - wh - 48))
        w.geometry(f"+{x}+{y}")

    def tick(self, animate):
        w = self.win
        if w is None or not w.winfo_exists():
            return
        age = time.time() - self.t0
        if age >= self.life:
            return self.hide()
        a = min(1.0, age / 0.25, (self.life - age) / 0.4)
        try:
            w.attributes("-alpha", max(0.0, a))
        except tk.TclError:
            pass
        if animate and len(self.frames) > 1:
            self.idx = (self.idx + 1) % len(self.frames)
            self.lab.configure(image=self.frames[self.idx])
        self.job = self.app.root.after(85, lambda: self.tick(animate))

    def hide(self):
        if self.job:
            try:
                self.app.root.after_cancel(self.job)
            except Exception:
                pass
            self.job = None
        if self.win is not None:
            try:
                self.win.destroy()
            except Exception:
                pass
            self.win = None


def reduced_motion():
    """Best effort: honour the OS 'reduce animations' setting."""
    try:
        if IS_WIN:
            import ctypes
            on = ctypes.c_int(1)
            ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(on), 0)   # SPI_GETCLIENTAREAANIMATION
            return not on.value
        if IS_MAC:
            r = subprocess.run(["defaults", "read", "com.apple.universalaccess", "reduceMotion"],
                               capture_output=True, text=True, timeout=2)
            return r.stdout.strip() == "1"
        r = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "enable-animations"],
                           capture_output=True, text=True, timeout=2)
        return r.stdout.strip() == "false"
    except Exception:
        return False


def beep(root):
    try:
        if IS_WIN:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        else:
            root.bell()
    except Exception:
        pass


# =============================================================================
# UI - widgets
# =============================================================================
class FloatTip:
    """One reusable floating tooltip window."""

    def __init__(self, app):
        self.app = app
        self.win = None

    def _ensure(self):
        if self.win is not None and self.win.winfo_exists():
            return
        self.win = tk.Toplevel(self.app.root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.frame = tk.Frame(self.win, bd=0)
        self.frame.pack()
        self.lbl = tk.Label(self.frame, justify="left", bd=0, padx=self.app.px(9), pady=self.app.px(6))
        self.lbl.pack(padx=1, pady=1)

    def show(self, text, x, y):
        if not text:
            return self.hide()
        self._ensure()
        th = self.app.th
        self.frame.configure(bg=th["border"])
        self.lbl.configure(text=text, bg=th["raised"], fg=th["ink"], font=self.app.f["small"])
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        bx0, by0, bx1, by1 = self.app.screen_bounds()
        nx, ny = x + 14, y + 18
        if nx + w > bx1:
            nx = x - w - 10
        if ny + h > by1:
            ny = y - h - 10
        self.win.geometry(f"+{int(max(bx0, nx))}+{int(max(by0, ny))}")
        self.win.deiconify()
        self.win.lift()

    def hide(self):
        if self.win is not None and self.win.winfo_exists():
            self.win.withdraw()


class IconButton(_Canvas):
    def __init__(self, parent, app, icon, command, tip, active=False, size=26):
        s = app.px(size)
        super().__init__(parent, width=s, height=s, bg=parent["bg"], highlightthickness=0, bd=0, cursor="hand2")
        self.app, self.icon, self.command, self.tiptext = app, icon, command, tip
        self.s, self.active, self.hover, self._job = s, active, False, None
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonRelease-1>", self._click)
        self.draw()

    def _enter(self, e):
        self.hover = True
        self.draw()
        self._job = self.after(550, lambda: self.app.tip.show(self.tiptext, e.x_root, e.y_root))

    def _leave(self, _e):
        self.hover = False
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        self.app.tip.hide()
        self.draw()

    def _click(self, e):
        if 0 <= e.x <= self.s and 0 <= e.y <= self.s:
            self.app.tip.hide()
            self.command()

    def set_active(self, on):
        self.active = on
        self.draw()

    def draw(self):
        app, th, s = self.app, self.app.th, self.s
        bg = self["bg"]
        if self.hover:
            tile = th["hover"] if bg != th["surface"] else th["raised"]
        elif self.active:
            tile = th["accent_soft"]
        else:
            tile = None
        col = th["accent"] if self.active else (th["ink"] if self.hover else th["ink2"])
        key = ("icon", self.icon, s, col, bg, tile, app.S)
        img = app.img(key, s, s, bg, lambda: self._shapes(col, bg, tile))
        self.delete("all")
        self.create_image(0, 0, image=img, anchor="nw")

    def _shapes(self, col, bg, tile):
        s, S = self.s, self.app.S
        hw = 0.72 * S                       # ~1.4px hairline stroke
        c, r = s / 2.0, s * 0.2
        base = tile or bg
        sh = []
        if tile:
            sh.append(g_rrect(s * 0.06, s * 0.06, s * 0.94, s * 0.94, s * 0.3, tile))
        ic = self.icon
        if ic == "close":
            sh += [g_line([(c - r, c - r), (c + r, c + r)], hw, col), g_line([(c - r, c + r), (c + r, c - r)], hw, col)]
        elif ic == "minimize":
            sh.append(g_line([(c - r, c + r * 0.3), (c + r, c + r * 0.3)], hw, col))
        elif ic == "expand":
            sh.append(g_rrect(c - r * 1.05, c - r * 0.85, c + r * 1.05, c + r * 0.85, s * 0.07, col, hw=hw))
        elif ic == "pin":
            top, mid, tip = c - r * 1.25, c - r * 0.05, c + r * 1.3
            sh.append(g_line([(c - r * 0.55, top), (c + r * 0.55, top)], hw, col))
            if self.active:
                sh.append(g_rrect(c - r * 0.45, top, c + r * 0.45, mid, r * 0.12, col))
            else:
                sh.append(g_rrect(c - r * 0.45, top, c + r * 0.45, mid, r * 0.12, col, hw=hw))
            sh.append(g_line([(c - r * 0.95, mid), (c + r * 0.95, mid)], hw, col))
            sh.append(g_line([(c, mid), (c, tip)], hw, col))
        elif ic == "sliders":
            k = r * 0.34
            for yy, xx in ((c - r * 0.55, c - r * 0.35), (c + r * 0.55, c + r * 0.4)):
                sh.append(g_line([(c - r, yy), (c + r, yy)], hw, col))
                sh.append(g_disc(xx, yy, k + hw, base))
                sh.append(g_ring(xx, yy, k, hw, col))
        elif ic == "refresh":
            rr = r * 1.1
            pts = []
            for i in range(0, 25):
                a = math.radians(35 + i * (285 / 24.0))
                pts.append((c + rr * math.cos(a), c - rr * math.sin(a)))
            sh.append(g_line(pts, hw, col))
            a = math.radians(320)
            tip = (c + rr * math.cos(a), c - rr * math.sin(a))
            tx, ty = -math.sin(a), -math.cos(a)           # direction of travel at the tip
            for da in (35, -35):
                t = math.radians(da)
                bx = -(tx * math.cos(t) - ty * math.sin(t))
                by = -(tx * math.sin(t) + ty * math.cos(t))
                sh.append(g_line([tip, (tip[0] + bx * r * 0.85, tip[1] + by * r * 0.85)], hw, col))
        return sh


class Pill(_Canvas):
    """Small rounded label (plan badge)."""

    def __init__(self, parent, app, fg, fill, edge, font="tinyb", padx=8, pady=2):
        self.app, self.fg, self.fill, self.edge, self.font = app, fg, fill, edge, font
        self.padx, self.pady = app.px(padx), app.px(pady)
        super().__init__(parent, bg=parent["bg"], highlightthickness=0, bd=0)
        self.set("")

    def set(self, text):
        app, f = self.app, self.app.f[self.font]
        w = f.measure(text) + 2 * self.padx
        h = f.metrics("linespace") + 2 * self.pady
        self.configure(width=w, height=h)
        bg = self["bg"]
        img = app.img(("pill", w, h, self.fill, self.edge, bg), w, h, bg, lambda: [
            g_rrect(0, 0, w, h, h / 2.0, self.edge), g_rrect(1, 1, w - 1, h - 1, h / 2.0 - 1, self.fill)])
        self.delete("all")
        self.create_image(0, 0, image=img, anchor="nw")
        self.create_text(w / 2.0, h / 2.0, text=text, font=f, fill=self.fg)


class Worker(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self.app = app
        self.wake = threading.Event()
        self.reset = False

    def run(self):
        app = self.app
        while True:
            cfg = dict(app.cfg)
            try:
                if self.reset:
                    self.reset = False
                    app.store = app.make_store()
                roots = log_roots(list(cfg.get("extra_paths") or []) + list(app.args.path or []))
                since = time.time() - (int(cfg.get("history_days", 30)) + 1) * 86400
                t0, last = time.time(), [0.0]

                def prog(i, n):
                    if time.time() - last[0] > 0.3:
                        last[0] = time.time()
                        app.q.put(("progress", i, n))

                changed, nfiles = app.store.scan(roots, since, prog)
                entries = app.store.entries(since)
                scan = {"roots": roots, "files": nfiles, "entries": len(entries), "secs": time.time() - t0,
                        "demo": app.store.demo, "cost_states": dict(getattr(app.store, "cost_states", {})),
                        "unpriced": dict(getattr(app.store, "unpriced", {}))}
                app.q.put(("snap", build_snapshot(entries, time.time(), cfg, app.live.get(), scan)))
            except Exception as ex:  # noqa: BLE001 - keep the widget alive, show the problem
                app.q.put(("error", f"{type(ex).__name__}: {ex}"))
            self.wake.wait(max(3, float(cfg.get("refresh_sec", 15))))
            self.wake.clear()


# =============================================================================
# UI - application
# =============================================================================
class App:
    TABS = (("overview", "Overview"), ("history", "History"), ("projects", "Projects"), ("sessions", "Sessions"))

    def __init__(self, root, cfg, args):
        self.root, self.cfg, self.args = root, cfg, args
        self.persist = not args.demo
        self.S = detect_scale(root)
        self.f = make_fonts(root)
        self.th = make_theme(cfg["theme"], cfg["accent"])
        self.W = self.px(392)
        self.CW = self.W - self.px(48) - 2
        self.q = queue.Queue()
        self.snap = self.progress = self.error = self.toast = self.banner = self.prev_win = None
        self._rings, self._save_job, self._frameless, self._drag = {}, None, None, None
        self.settings = None
        self.store = self.make_store()
        self.live = DemoLive(args.demo) if args.demo else LiveLimits(self)
        self.tip = FloatTip(self)
        self.mascot = Mascot(self)
        self.topmost_var = tk.BooleanVar(value=bool(cfg["topmost"]))
        root.title(APP_NAME)
        root.resizable(False, False)
        self.apply_window_attrs()
        self.build()
        self.bind_keys()
        self.place_window()
        self.worker = Worker(self)
        self.worker.start()
        threading.Thread(target=self.live.loop, daemon=True).start()
        root.protocol("WM_DELETE_WINDOW", self.quit)
        root.after(120, self.poll)
        if getattr(args, "open_settings", False):
            root.after(600, self.open_settings)
        elif getattr(args, "setup", False) or (not args.demo and not cfg.get("welcomed")):
            root.after(900, self.open_welcome)

    # ---------------------------------------------------------------- basics
    def px(self, n):
        return int(round(n * self.S))

    def img(self, key, w, h, bg, build):
        """Cached anti-aliased PhotoImage; build() returns the shape list."""
        cache = self.__dict__.setdefault("_gimgs", {})
        im = cache.get(key)
        if im is None:
            im = tk.PhotoImage(master=self.root, width=max(1, w), height=max(1, h))
            im.put(render_gfx(max(1, w), max(1, h), bg, build()))
            if len(cache) > 400:
                cache.clear()
            cache[key] = im
        return im

    def make_store(self):
        return DemoStore() if self.args.demo else LogStore(self.cfg.get("price_overrides"))

    def save_soon(self):
        if not self.persist:
            return
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(700, lambda: save_config(self.cfg))

    def screen_bounds(self):
        if IS_WIN:
            try:
                import ctypes
                gm = ctypes.windll.user32.GetSystemMetrics
                x, y, w, h = gm(76), gm(77), gm(78), gm(79)
                if w and h:
                    return x, y, x + w, y + h
            except Exception:  # noqa: BLE001
                pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def apply_window_attrs(self):
        r = self.root
        for attr, val in (("-topmost", bool(self.cfg["topmost"])), ("-alpha", float(self.cfg["opacity"]))):
            try:
                r.attributes(attr, val)
            except tk.TclError:
                pass
        want = bool(self.cfg["frameless"])
        if want != self._frameless:
            mapped = self._frameless is not None and r.winfo_ismapped()
            if mapped:
                r.withdraw()
            r.overrideredirect(want)
            if mapped:
                r.deiconify()
            self._frameless = want
            if IS_WIN:
                r.after(60, self.win_tweaks)

    def win_tweaks(self):
        """Windows: rounded corners (Win 11), taskbar button for the borderless window, dark title bar."""
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
            val = ctypes.c_int(2)
            dwm(hwnd, 33, ctypes.byref(val), ctypes.sizeof(val))
            dark = ctypes.c_int(1 if self.th["name"] == "dark" else 0)
            dwm(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
            if self._frameless:
                style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
                ctypes.windll.user32.SetWindowLongW(hwnd, -20, (style & ~0x80) | 0x40000)
                self.root.withdraw()
                self.root.after(10, self.root.deiconify)
        except Exception:  # noqa: BLE001 - purely cosmetic
            pass

    def place_window(self):
        r = self.root
        r.update_idletasks()
        w, h = r.winfo_reqwidth(), r.winfo_reqheight()
        x0, y0, x1, y1 = self.screen_bounds()
        x, y = self.cfg.get("x"), self.cfg.get("y")
        if not isinstance(x, int) or not isinstance(y, int) or not (x0 - w + 60 <= x <= x1 - 60) \
                or not (y0 <= y <= y1 - 60):
            x, y = x1 - w - self.px(24), y0 + self.px(56)
        r.geometry(f"+{x}+{y}")

    # ---------------------------------------------------------------- build
    def build(self):
        self.tip.hide()
        for w in list(self.root.winfo_children()):
            if w is not self.tip.win and not (self.settings and w is self.settings.win):
                w.destroy()
        th = self.th = make_theme(self.cfg["theme"], self.cfg["accent"])
        self.root.configure(bg=th["border"])
        self.shell = tk.Frame(self.root, bg=th["bg"])
        self.shell.pack(fill="both", expand=True, padx=1, pady=1)
        self.full = tk.Frame(self.shell, bg=th["bg"])
        self.minif = tk.Frame(self.shell, bg=th["surface"])
        tk.Frame(self.full, bg=th["bg"], width=self.W, height=0).pack()
        self.build_titlebar()
        self.banner_slot = tk.Frame(self.full, bg=th["bg"])
        self.banner_slot.pack(fill="x")
        self.build_tabbar()
        # fixed-width, scrollable content area (keeps the window narrow and on-screen)
        cw = self.W - self.px(20)
        self.holder = tk.Canvas(self.full, bg=th["bg"], highlightthickness=0, bd=0, width=cw,
                                height=self.px(120), yscrollincrement=self.px(24))
        self.holder.pack(anchor="w", padx=(self.px(10), 0), pady=(self.px(10), 0))
        self.content = tk.Frame(self.holder, bg=th["bg"])
        self.holder.create_window(0, 0, window=self.content, anchor="nw", width=cw)
        self.sbar = tk.Canvas(self.full, width=self.px(4), height=10, bg=th["bg"], highlightthickness=0, bd=0)
        self.sbar.place(in_=self.holder, relx=1.0, x=self.px(3), y=0, relheight=1.0, anchor="nw")
        self.scrollable, self._rendered_tab = False, None
        self.build_footer()
        self.build_mini()
        self.menu = tk.Menu(self.root, tearoff=0, bg=th["surface"], fg=th["ink"], bd=0, relief="flat",
                            activebackground=th["accent_soft"], activeforeground=th["ink"],
                            selectcolor=th["accent"], font=self.f["body"])
        self.show_mode()
        self.render()

    def build_titlebar(self):
        th, f, px = self.th, self.f, self.px
        bar = tk.Frame(self.full, bg=th["bg"], height=px(40))
        bar.pack(fill="x")
        bar.pack_propagate(False)
        left = tk.Frame(bar, bg=th["bg"])
        left.pack(side="left", padx=(px(12), 0))
        self.dot = tk.Canvas(left, width=px(14), height=px(14), bg=th["bg"], highlightthickness=0, bd=0)
        self.dot.pack(side="left")
        title = tk.Label(left, text=APP_NAME, font=f["title"], fg=th["ink"], bg=th["bg"])
        title.pack(side="left", padx=(px(5), px(8)))
        self.badge = Pill(left, self, th["accent"], th["accent_soft"], mix(th["accent_soft"], th["accent"], 0.45))
        right = tk.Frame(bar, bg=th["bg"])
        right.pack(side="right", padx=(0, px(6)))
        IconButton(right, self, "close", self.quit, "Quit  (Ctrl+Q)").pack(side="right")
        IconButton(right, self, "minimize", self.toggle_mini, "Mini view  (M)").pack(side="right")
        self.pin_btn = IconButton(right, self, "pin", self.toggle_topmost, "Always on top  (T)",
                                  active=self.cfg["topmost"])
        self.pin_btn.pack(side="right")
        IconButton(right, self, "sliders", self.open_settings, "Settings  (S)").pack(side="right")
        IconButton(right, self, "refresh", self.refresh_now, "Refresh  (R)").pack(side="right")
        for w in (bar, left, title, self.dot, self.badge):
            self.make_draggable(w)
            w.bind("<Double-Button-1>", lambda e: self.toggle_mini())
        self.dot.bind("<Enter>", lambda e: self.tip.show(self.status_text(), e.x_root, e.y_root))
        self.dot.bind("<Leave>", lambda e: self.tip.hide())

    def build_tabbar(self):
        th, f, px = self.th, self.f, self.px
        bar = tk.Frame(self.full, bg=th["bg"])
        bar.pack(fill="x", padx=px(14))
        self.tabw = {}
        for key, label in self.TABS:
            cell = tk.Frame(bar, bg=th["bg"], cursor="hand2")
            cell.pack(side="left", padx=(0, px(18)))
            lab = tk.Label(cell, text=label, font=f["bodyb"], bg=th["bg"], cursor="hand2")
            lab.pack(pady=(0, px(6)))
            line = tk.Frame(cell, height=px(2), bg=th["bg"])
            line.pack(fill="x")
            for w in (cell, lab):
                w.bind("<Button-1>", lambda e, k=key: self.set_tab(k))
            lab.bind("<Enter>", lambda e, k=key: self._tab_hover(k, True))
            lab.bind("<Leave>", lambda e, k=key: self._tab_hover(k, False))
            self.tabw[key] = (lab, line)
        tk.Frame(self.full, bg=th["border"], height=1).pack(fill="x", padx=px(12))
        self.style_tabs()

    def _tab_hover(self, key, on):
        if key != self.cfg["tab"]:
            self.tabw[key][0].configure(fg=self.th["ink2"] if on else self.th["muted"])

    def style_tabs(self):
        for key, (lab, line) in self.tabw.items():
            on = key == self.cfg["tab"]
            lab.configure(fg=self.th["ink"] if on else self.th["muted"])
            line.configure(bg=self.th["accent"] if on else self.th["bg"])

    def build_footer(self):
        th, f, px = self.th, self.f, self.px
        bar = tk.Frame(self.full, bg=th["bg"])
        bar.pack(fill="x", padx=px(14), pady=(px(1), px(9)))
        self.foot_l = tk.Label(bar, text="", font=f["tiny"], fg=th["muted"], bg=th["bg"], anchor="w")
        self.foot_l.pack(side="left")
        self.foot_r = tk.Label(bar, text="", font=f["tiny"], fg=th["muted"], bg=th["bg"], anchor="e")
        self.foot_r.pack(side="right")

    def build_mini(self):
        th, f, px = self.th, self.f, self.px
        inner = tk.Frame(self.minif, bg=th["surface"])
        inner.pack(padx=(px(8), px(4)), pady=px(6))
        self.mini_ring = tk.Canvas(inner, width=px(36), height=px(36), bg=th["surface"], highlightthickness=0, bd=0)
        self.mini_ring.pack(side="left")
        txt = tk.Frame(inner, bg=th["surface"])
        txt.pack(side="left", padx=(px(9), px(10)))
        self.mini_top = tk.Label(txt, text="", font=f["bodyb"], fg=th["ink"], bg=th["surface"], anchor="w")
        self.mini_top.pack(anchor="w")
        self.mini_sub = tk.Label(txt, text="", font=f["tiny"], fg=th["muted"], bg=th["surface"], anchor="w")
        self.mini_sub.pack(anchor="w")
        IconButton(inner, self, "expand", self.toggle_mini, "Full view  (M)").pack(side="left")
        for w in (self.minif, inner, self.mini_ring, txt, self.mini_top, self.mini_sub):
            self.make_draggable(w)
            w.bind("<Double-Button-1>", lambda e: self.toggle_mini())
        self.mini_ring.bind("<Enter>", lambda e: self.tip.show(self.ring_tip(), e.x_root, e.y_root))
        self.mini_ring.bind("<Leave>", lambda e: self.tip.hide())

    def bind_keys(self):
        r = self.root
        for seq, fn in (("<KeyPress-r>", self.refresh_now), ("<KeyPress-m>", self.toggle_mini),
                        ("<KeyPress-t>", self.toggle_topmost), ("<KeyPress-s>", self.open_settings),
                        ("<Escape>", lambda: None if self.cfg["mini"] else self.toggle_mini()),
                        ("<Control-q>", self.quit)):
            r.bind(seq, lambda e, fn=fn: fn())
        for i, (key, _l) in enumerate(self.TABS, 1):
            r.bind(f"<KeyPress-{i}>", lambda e, k=key: self.set_tab(k))
        r.bind("<ButtonPress-1>", lambda e: self._focus(), add="+")
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            r.bind(seq, self.on_wheel)
        r.bind("<Button-3>", self.popup_menu)
        if IS_MAC:
            r.bind("<Button-2>", self.popup_menu)
            r.bind("<Control-Button-1>", self.popup_menu)

    def _focus(self):
        try:
            if self.root.focus_get() is None:
                self.root.focus_force()
        except (KeyError, tk.TclError):
            pass

    def on_wheel(self, e):
        if self.cfg["mini"] or not self.scrollable:
            return
        num = getattr(e, "num", None)
        d = -1 if num == 4 else 1 if num == 5 else (-1 if e.delta > 0 else 1)
        self.tip.hide()
        self.holder.yview_scroll(d * 2, "units")
        self.draw_sbar()

    def fit_content(self, top=0.0):
        """Size the content viewport to its content, capped to the space left on screen."""
        r = self.root
        self.content.update_idletasks()
        ch = max(1, self.content.winfo_reqheight())
        _x0, y0, _x1, y1 = self.screen_bounds()
        other = self.full.winfo_reqheight() - int(float(self.holder["height"]))
        y = r.winfo_y() if r.winfo_ismapped() else y0 + self.px(56)
        avail = (y1 - self.px(12)) - max(y0, y) - other - 2
        h = max(self.px(240), min(ch, avail))
        self.scrollable = ch > h + 1
        self.holder.configure(height=h, scrollregion=(0, 0, self.W - self.px(20), ch))
        self.holder.yview_moveto(top if self.scrollable else 0.0)
        self.draw_sbar()

    def draw_sbar(self):
        c = self.sbar
        c.delete("all")
        if not self.scrollable:
            return
        f0, f1 = self.holder.yview()
        h, w = float(self.holder["height"]), self.px(4)
        c.create_line(w / 2.0, max(w / 2.0, f0 * h + w / 2.0), w / 2.0, min(h - w / 2.0, f1 * h - w / 2.0),
                      width=w - 1, capstyle="round", fill=self.th["base"])

    def keep_on_screen(self, before):
        """After a size change keep the right edge fixed (when docked right) and stay inside the screen."""
        r = self.root
        r.update_idletasks()
        bx, bw = before
        x0, y0, x1, y1 = self.screen_bounds()
        w, h = r.winfo_reqwidth(), r.winfo_reqheight()
        x, y = r.winfo_x(), r.winfo_y()
        if bw and bw != w and bx + bw / 2 > (x0 + x1) / 2:
            x = bx + bw - w
        x = int(min(max(x0, x), x1 - w))
        y = int(min(max(y0, y), max(y0, y1 - h)))
        if (x, y) != (r.winfo_x(), r.winfo_y()):
            r.geometry(f"+{x}+{y}")

    # ---------------------------------------------------------------- drag / mode
    def make_draggable(self, w):
        w.bind("<ButtonPress-1>", self._drag_start, add="+")
        w.bind("<B1-Motion>", self._drag_move)
        w.bind("<ButtonRelease-1>", self._drag_end, add="+")

    def _drag_start(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y(), False)

    def _drag_move(self, e):
        if self._drag:
            self.root.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")
            self._drag = (self._drag[0], self._drag[1], True)

    def _drag_end(self, _e):
        if self._drag and self._drag[2]:
            self.snap_to_edges()
            self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
            self.save_soon()
        self._drag = None

    def snap_to_edges(self):
        x0, y0, x1, y1 = self.screen_bounds()
        x, y = self.root.winfo_x(), self.root.winfo_y()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        m, t = self.px(8), self.px(28)
        if abs(x - x0) < t:
            x = x0 + m
        elif abs(x1 - (x + w)) < t:
            x = x1 - w - m
        if abs(y - y0) < t:
            y = y0 + m
        elif abs(y1 - (y + h)) < t:
            y = y1 - h - m
        self.root.geometry(f"+{x}+{y}")

    def show_mode(self):
        if self.cfg["mini"]:
            self.full.pack_forget()
            self.minif.pack(fill="both")
        else:
            self.minif.pack_forget()
            self.full.pack(fill="both")

    def toggle_mini(self):
        r = self.root
        r.update_idletasks()
        x0, _y0, x1, _y1 = self.screen_bounds()
        old_x, old_w = r.winfo_x(), r.winfo_width()
        anchor_right = old_x + old_w / 2 > (x0 + x1) / 2
        self.cfg["mini"] = not self.cfg["mini"]
        self.show_mode()
        self.render()
        r.update_idletasks()
        nx = old_x + old_w - r.winfo_reqwidth() if anchor_right else old_x
        r.geometry(f"+{int(nx)}+{r.winfo_y()}")
        self.cfg["x"] = int(nx)
        self.save_soon()

    def toggle_topmost(self):
        self.cfg["topmost"] = not self.cfg["topmost"]
        self.topmost_var.set(self.cfg["topmost"])
        self.apply_window_attrs()
        self.pin_btn.set_active(self.cfg["topmost"])
        self.flash_toast("Always on top: " + ("on" if self.cfg["topmost"] else "off"))
        self.save_soon()

    def set_tab(self, key):
        if self.cfg["mini"]:
            self.toggle_mini()
        self.cfg["tab"] = key
        self.style_tabs()
        self.render()
        self.save_soon()

    def set_cfg(self, key, value):
        self.cfg[key] = value
        self.save_soon()
        self.render()

    def refresh_now(self):
        self.worker.wake.set()
        self.live.wake.set()
        self.flash_toast("Refreshing…")

    def flash_toast(self, text, secs=2.5):
        self.toast = (text, time.time() + secs)
        self.update_footer()
        self.root.after(int(secs * 1000) + 50, self.update_footer)

    def popup_menu(self, e):
        m = self.menu
        m.delete(0, "end")
        m.add_command(label="Refresh now", accelerator="R", command=self.refresh_now)
        m.add_command(label="Full view" if self.cfg["mini"] else "Mini view", accelerator="M",
                      command=self.toggle_mini)
        m.add_checkbutton(label="Always on top", accelerator="T", variable=self.topmost_var,
                          command=lambda: (self.topmost_var.set(not self.topmost_var.get()), self.toggle_topmost()))
        m.add_separator()
        for i, (key, label) in enumerate(self.TABS, 1):
            m.add_command(label=label, accelerator=str(i), command=lambda k=key: self.set_tab(k))
        m.add_separator()
        if float(self.cfg.get("snooze_until") or 0) > time.time():
            m.add_command(label="Resume alerts", command=lambda: self.snooze(0))
        else:
            sn = tk.Menu(m, tearoff=0, bg=self.th["surface"], fg=self.th["ink"], bd=0, relief="flat",
                         activebackground=self.th["accent_soft"], activeforeground=self.th["ink"], font=self.f["body"])
            for label, mins in (("30 minutes", 30), ("1 hour", 60), ("2 hours", 120), ("4 hours", 240)):
                sn.add_command(label=label, command=lambda mm=mins: self.snooze(mm))
            m.add_cascade(label="Snooze alerts", menu=sn)
        m.add_command(label="Export CSV…", command=self.export_csv)
        m.add_command(label="Open logs folder", command=self.open_logs)
        m.add_command(label="Settings…", accelerator="S", command=self.open_settings)
        m.add_separator()
        m.add_command(label="Quit", accelerator="Ctrl+Q", command=self.quit)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    # ---------------------------------------------------------------- data loop
    def poll(self):
        got = False
        try:
            while True:
                item = self.q.get_nowait()
                if item[0] == "snap":
                    self.snap, self.progress, self.error, got = item[1], None, None, True
                elif item[0] == "progress":
                    self.progress = (item[1], item[2])
                    self.update_footer()
                elif item[0] == "mascot":
                    self.mascot.show(*item[1:])
                elif item[0] == "error":
                    self.error, self.progress = item[1], None
                    self.update_footer()
        except queue.Empty:
            pass
        if got:
            self.render()
            self.check_alerts(self.snap)
        self.root.after(250, self.poll)

    def render(self):
        s = self.snap
        r = self.root
        before = (r.winfo_x(), r.winfo_width()) if r.winfo_ismapped() else (0, 0)
        self.update_title(s)
        if self.cfg["mini"]:
            self.render_mini(s)
        else:
            self.tip.hide()
            same = self._rendered_tab == self.cfg["tab"]
            top = self.holder.yview()[0] if same else 0.0
            for w in self.content.winfo_children():
                w.destroy()
            getattr(self, "render_" + self.cfg["tab"], self.render_overview)(s)
            self._rendered_tab = self.cfg["tab"]
            self.render_banner()
            self.update_footer()
            self.fit_content(top)
        if r.winfo_ismapped():
            self.keep_on_screen(before)

    def status_text(self):
        live = self.live.get()
        st = live.get("status")
        if self.args.demo:
            return "Demo data"
        if st == "ok":
            return f"Live plan limits · updated {fmt_ago(time.time() - live.get('fetched', time.time()))}"
        if st == "stale":
            return "Live plan limits (stale) · " + (live.get("msg") or "")
        if st == "off":
            return "Local logs only (live plan limits off)"
        if st == "idle":
            return "Checking plan limits…"
        return "Local logs only · " + (live.get("msg") or "")

    def update_title(self, s):
        th, px = self.th, self.px
        live = (s or {}).get("live") or self.live.get()
        col = {"ok": STATUS["good"], "stale": STATUS["warn"]}.get(live.get("status"), th["muted"])
        dsz = px(14)
        dimg = self.img(("dot", dsz, col, th["bg"]), dsz, dsz, th["bg"], lambda: [
            g_disc(dsz / 2.0, dsz / 2.0, dsz / 2.0 - 0.5, mix(th["bg"], col, 0.22)),
            g_disc(dsz / 2.0, dsz / 2.0, dsz * 0.29, col)])
        self.dot.delete("all")
        self.dot.create_image(0, 0, image=dimg, anchor="nw")
        plan = live.get("plan")
        if plan:
            self.badge.set(plan.upper())
            if not self.badge.winfo_manager():
                self.badge.pack(side="left")
        elif self.badge.winfo_manager():
            self.badge.pack_forget()
        g = (s or {}).get("gauge") or {}
        title = APP_NAME if g.get("pct") is None else f"{g['pct']:.0f}% · {APP_NAME}"
        self.root.title(title)

    def update_footer(self):
        if self.cfg["mini"]:
            return
        s = self.snap
        if self.toast and time.time() < self.toast[1]:
            left = self.toast[0]
        elif self.progress:
            left = f"Reading logs… {self.progress[0]:,} / {self.progress[1]:,} files"
        elif self.error:
            left = "Problem: " + self.error[:70]
        elif s and s.get("unpriced") and 8 <= int(time.time()) % 30 < 16:
            names = ", ".join(sorted(s["unpriced"])[:2])
            left = f"Price is a guess for {names} - set price_overrides"
        elif s and s.get("coverage") and s["coverage"] < 0.97 and int(time.time()) % 30 < 8:
            left = f"Logs match ~{s['coverage'] * 100:.0f}% of Claude Code's own cost record"
        elif s:
            sc = s["scan"]
            if sc.get("demo"):
                left = f"Demo data · updated {fmt_clock(s['now'])}"
            else:
                left = (f"Updated {fmt_clock(s['now'])} · {sc['entries']:,} msgs · {sc['files']:,} "
                        f"file{'' if sc['files'] == 1 else 's'}")
        else:
            left = "Starting…"
        right = METRIC_NAME.get(self.cfg["metric"], "")
        room = self.W - self.px(32)
        if self.f["tiny"].measure(left) + self.f["tiny"].measure(right) + self.px(16) > room:
            right = ""
        self.foot_l.configure(text=self.elide(left, self.f["tiny"], room))
        self.foot_r.configure(text=right)

    # ---------------------------------------------------------------- building blocks
    def card(self, parent, title=None, right=None):
        th, px = self.th, self.px
        outer = tk.Frame(parent, bg=th["border"], bd=0, highlightthickness=0)
        outer.pack(fill="x", pady=(0, px(9)))
        inner = tk.Frame(outer, bg=th["surface"], bd=0, highlightthickness=0)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        head = None
        if title:
            head = tk.Frame(inner, bg=th["surface"])
            head.pack(fill="x", padx=px(14), pady=(px(12), 0))
            tk.Label(head, text=title.upper(), font=self.f["label"], fg=th["muted"], bg=th["surface"]).pack(side="left")
            if right:
                tk.Label(head, text=right, font=self.f["tiny"], fg=th["muted"], bg=th["surface"]).pack(side="right")
        body = tk.Frame(inner, bg=th["surface"])
        body.pack(fill="x", padx=px(14), pady=(px(9) if title else px(13), px(13)))
        self.round_corners(outer, parent["bg"], px(11))
        return body, head

    def round_corners(self, outer, outside, r):
        """Overlay four anti-aliased corner tiles on a 1px-bordered frame."""
        th = self.th
        for fx, fy, kw in ((0, 0, dict(x=0, y=0, anchor="nw")), (1, 0, dict(relx=1, x=0, y=0, anchor="ne")),
                           (0, 1, dict(rely=1, x=0, y=0, anchor="sw")), (1, 1, dict(relx=1, rely=1, anchor="se"))):
            key = ("corner", r, fx, fy, outside, th["border"], th["surface"])
            cx, cy = (0 if fx else r), (0 if fy else r)
            im = self.img(key, r, r, outside, lambda cx=cx, cy=cy: [
                g_disc(cx, cy, r, th["border"]), g_disc(cx, cy, r - 1, th["surface"])])
            t = tk.Label(outer, image=im, bd=0, highlightthickness=0, bg=outside)
            t.image = im
            t.place(**kw)
            t.lift()

    def lbl(self, parent, text, font="small", fg="ink", **kw):
        bg = kw.pop("bg", None) or parent["bg"]
        return tk.Label(parent, text=text, font=self.f[font], fg=self.th.get(fg, fg), bg=bg, **kw)

    def shape(self, parent, kind, color, size=8):
        s_, bg = self.px(size), parent["bg"]
        c = tk.Canvas(parent, width=s_, height=s_, bg=bg, highlightthickness=0, bd=0)

        def build():
            m = s_ / 2.0
            if kind == "triangle":
                return [g_poly([(m, s_ * 0.2), (s_ * 0.84, s_ * 0.8), (s_ * 0.16, s_ * 0.8)], color, grow=s_ * 0.07)]
            if kind == "square":
                return [g_rrect(s_ * 0.1, s_ * 0.1, s_ * 0.9, s_ * 0.9, s_ * 0.2, color)]
            if kind == "ring":
                return [g_ring(m, m, s_ * 0.34, max(0.6, 0.75 * self.S), color)]
            if kind == "swatch":
                return [g_rrect(0, 0, s_, s_, s_ * 0.28, color)]
            return [g_disc(m, m, s_ * 0.44, color)]

        im = self.img(("shape", kind, s_, color, bg), s_, s_, bg, build)
        c.create_image(0, 0, image=im, anchor="nw")
        c.img = im
        return c

    def chip(self, parent, sev):
        fr = tk.Frame(parent, bg=parent["bg"])
        fr.pack(side="right")
        self.shape(fr, sev[3], sev[1]).pack(side="left", padx=(0, self.px(5)))
        self.lbl(fr, sev[2], "tinyb", "ink2").pack(side="left")

    def legend(self, head, fams):
        if len(fams) < 2:
            return
        for fam in reversed(fams):
            self.lbl(head, FAM_LABEL[fam], "tiny", "ink2").pack(side="right", padx=(self.px(4), 0))
            self.shape(head, "swatch", self.th["series"][fam], 7).pack(side="right", padx=(self.px(10), 0))

    def meter(self, parent, frac, color, width=None, height=6, track=None, marker=None, ticks=0):
        th, S = self.th, self.S
        h, w = self.px(height), width or self.CW
        pad = self.px(3) if marker is not None else 0
        H = h + 2 * pad
        bg = parent["bg"]
        frac = round(max(0.0, min(1.0, frac)) * 1000) / 1000.0
        mk = None if marker is None else round(min(1.0, max(0.0, marker)) * 1000) / 1000.0
        trk = track or th["grid"]
        key = ("meter", w, H, h, frac, color, trk, bg, mk, ticks, th["ink"], S)

        def build():
            sh = [g_rrect(0, pad, w, pad + h, h / 2.0, trk)]
            if frac > 0:
                sh.append(g_rrect(0, pad, max(h * 0.9, w * frac), pad + h, h / 2.0, color))
            for i in range(1, ticks):   # period dividers (hours of the window / days of the week)
                x = w * i / float(ticks)
                sh.append(g_rect(x - 0.5, pad, x + 0.5, pad + h, bg))
            if mk is not None:          # how much of the period has elapsed
                hw = max(0.6, 0.75 * S)
                x = min(w - hw, max(hw, w * mk))
                sh.append(g_line([(x, hw), (x, H - hw)], hw, th["ink"]))
            return sh

        im = self.img(key, w, H, bg, build)
        c = tk.Canvas(parent, width=w, height=H, bg=bg, highlightthickness=0, bd=0)
        c.create_image(0, 0, image=im, anchor="nw")
        c.img = im
        return c

    def segmented(self, parent, options, value, command):
        th, px = self.th, self.px
        outer = tk.Frame(parent, bg=th["border"])
        inner = tk.Frame(outer, bg=th["seg_bg"])
        inner.pack(padx=1, pady=1)
        for key, label in options:
            on = key == value
            l = tk.Label(inner, text=label, font=self.f["smallb"] if on else self.f["small"],
                         fg=th["ink"] if on else th["muted"], bg=th["seg_sel"] if on else th["seg_bg"],
                         padx=px(10), pady=px(3), cursor="hand2")
            l.pack(side="left", padx=px(2), pady=px(2))
            l.bind("<ButtonRelease-1>", lambda e, k=key: command(k))
            if not on:
                l.bind("<Enter>", lambda e, w=l: w.configure(fg=th["ink2"]))
                l.bind("<Leave>", lambda e, w=l: w.configure(fg=th["muted"]))
        return outer

    def button(self, parent, text, command, primary=False):
        th, px = self.th, self.px
        bg = th["accent"] if primary else th["seg_bg"]
        hov = mix(bg, "#ffffff", 0.12) if th["name"] == "dark" or primary else mix(bg, "#000000", 0.05)
        outer = tk.Frame(parent, bg=th["accent"] if primary else th["border"])
        on_acc = "#14130f" if _lum(th["accent"]) > 0.45 else "#ffffff"
        l = tk.Label(outer, text=text, font=self.f["smallb"], fg=on_acc if primary else th["ink"], bg=bg,
                     padx=px(11), pady=px(4), cursor="hand2")
        l.pack(padx=1, pady=1)
        l.bind("<Enter>", lambda e: l.configure(bg=hov))
        l.bind("<Leave>", lambda e: l.configure(bg=bg))
        l.bind("<ButtonRelease-1>", lambda e: command())
        return outer

    def draw_ring(self, canvas, size, frac, color, inner_frac=None, thick=None):
        th, px = self.th, self.px
        thick = thick or px(11)
        frac = round(frac * 500) / 500.0                      # quantise so the cache actually hits
        inner_frac = None if inner_frac is None else round(inner_frac * 200) / 200.0
        R = size / 2.0 - thick / 2.0 - 1
        rings = [{"R": R, "h": thick / 2.0, "frac": frac, "fill": color, "track": mix(th["surface"], color, 0.2)}]
        if inner_frac is not None:
            it = max(2.0, px(3))
            rings.append({"R": R - thick / 2.0 - px(5) - it / 2.0, "h": it / 2.0, "frac": inner_frac,
                          "fill": th["muted"], "track": th["grid"]})
        key = (size, thick, round(frac, 3), color, th["surface"],
               None if inner_frac is None else round(inner_frac, 3))
        img = self._rings.get(key)
        if img is None:
            img = tk.PhotoImage(master=self.root, width=size, height=size)
            img.put(ring_data(size, rings, th["surface"]))
            if len(self._rings) > 24:
                self._rings.clear()
            self._rings[key] = img
        canvas.delete("all")
        canvas.create_image(size // 2, size // 2, image=img)
        canvas.img = img

    def ring_tip(self):
        s = self.snap
        if not s or not s["window"]:
            return "No active 5-hour window"
        w, g = s["window"], s["gauge"]
        src = {"live": "of your plan's 5-hour limit", "auto": "of your busiest past window",
               "custom": "of your custom limit"}.get(g["src"], "")
        first = f"Outer ring: {g['pct']:.0f}% {src}" if g["pct"] is not None else "Outer ring: no limit known yet"
        return f"{first}\nInner ring: {w['elapsed'] * 100:.0f}% of the window's time has passed"

    def empty_card(self, title, detail=""):
        body, _ = self.card(self.content)
        self.lbl(body, title, "bodyb").pack(anchor="w")
        if detail:
            self.lbl(body, detail, "small", "muted", justify="left", wraplength=self.CW).pack(anchor="w", pady=(self.px(4), 0))

    def no_data(self, s):
        if s is None:
            self.empty_card("Reading your Claude Code logs…", "This takes a few seconds the first time.")
            return True
        if not s["has_data"]:
            roots = s["scan"]["roots"]
            if roots:
                detail = "Looked in:\n" + "\n".join(shorten_path(r) for r in roots)
            else:
                detail = ("No Claude Code log folder found (~/.claude/projects or ~/.config/claude/projects). "
                          "Use Claude Code once, or add a folder in Settings.")
            self.empty_card(f"No Claude Code usage in the last {self.cfg['history_days']} days", detail)
            return True
        return False

    # ---------------------------------------------------------------- overview
    def render_overview(self, s):
        th, f, px = self.th, self.f, self.px
        if s is None or (not s["has_data"] and not s["window"]):
            self.no_data(s)
            if s is not None:
                self.render_limits_card(s)
            return
        metric, w, g = s["metric"], s["window"], s["gauge"]
        sev = severity(g["pct"] if w else None, th)

        body, head = self.card(self.content, "Current 5-hour window")
        self.chip(head, outlook(g, w, th))
        row = tk.Frame(body, bg=th["surface"])
        row.pack(fill="x")
        size = px(116)
        ring = tk.Canvas(row, width=size, height=size, bg=th["surface"], highlightthickness=0, bd=0)
        ring.pack(side="left", anchor="n")
        pct = g["pct"] if w else None
        self.draw_ring(ring, size, (pct or 0) / 100.0, sev[1], w["elapsed"] if w else 0.0)
        if pct is not None:
            ring.create_text(size / 2, size / 2 - px(5), text=f"{pct:.0f}%", font=f["hero"], fill=th["ink"])
            cap = {"live": "of plan", "auto": "of record", "custom": "of limit"}.get(g["src"], "")
            ring.create_text(size / 2, size / 2 + px(15), text=cap, font=f["tiny"], fill=th["muted"])
        else:
            ring.create_text(size / 2, size / 2 - px(5), text="—", font=f["hero"], fill=th["muted"])
            ring.create_text(size / 2, size / 2 + px(15), text="idle" if not w else "no limit yet",
                             font=f["tiny"], fill=th["muted"])
        ring.bind("<Enter>", lambda e: self.tip.show(self.ring_tip(), e.x_root, e.y_root))
        ring.bind("<Leave>", lambda e: self.tip.hide())

        st = tk.Frame(row, bg=th["surface"])
        st.pack(side="left", fill="both", expand=True, padx=(px(14), 0))
        if w:
            self.lbl(st, fmt_metric(w["val"], metric), "h1").pack(anchor="w")
            second = f"{fmt_tokens(tok(w['agg']))} tokens" if metric == "cost" else fmt_cost(w["agg"][4])
            self.lbl(st, f"{second} · {w['agg'][5]:,} msgs", "small", "ink2").pack(anchor="w", pady=(0, px(7)))
            grid = tk.Frame(st, bg=th["surface"])
            grid.pack(anchor="w", fill="x")
            rows = [("Resets", f"in {fmt_dur(w['remaining'])} · {fmt_clock(w['end'])}", False)]
            if w["rate_tokens"] > 0:
                a, b = f"{fmt_cost(w['rate_cost_h'])}/h", f"{fmt_tokens(w['rate_tokens'])} tok/min"
                rows.append(("Pace", f"{a} · {b}" if metric == "cost" else f"{b} · {a}", False))
                proj = fmt_metric(w["proj"], metric)
                if g["proj_pct"] is not None and g["src"] == "live":
                    proj = f"~{g['proj_pct']:.0f}% of plan"
                elif g["proj_pct"] is not None:
                    proj += f" · {g['proj_pct']:.0f}%"
                rows.append(("By reset", proj, (g["proj_pct"] or 0) >= 100))
            else:
                last = w["last"]
                rows.append(("Pace", "idle " + fmt_ago(s["now"] - last).replace(" ago", "") if last else "no activity yet",
                             False))
            if g["eta"]:
                rows.append(("Limit", f"~{fmt_clock(g['eta'])} at this pace", True))
            for i, (k, v, warn) in enumerate(rows):
                self.lbl(grid, k, "tiny", "muted", anchor="w").grid(row=i, column=0, sticky="w", pady=px(1))
                vf = tk.Frame(grid, bg=th["surface"])
                vf.grid(row=i, column=1, sticky="w", padx=(px(8), 0))
                if warn:
                    self.shape(vf, "triangle", STATUS["warn"], 8).pack(side="left", padx=(0, px(4)))
                self.lbl(vf, v, "small").pack(side="left")
        else:
            self.lbl(st, "Idle", "h1").pack(anchor="w")
            self.lbl(st, "Your next message starts a fresh 5-hour window.", "small", "ink2", justify="left",
                     wraplength=self.CW - size - px(16)).pack(anchor="w", pady=(0, px(8)))
            grid = tk.Frame(st, bg=th["surface"])
            grid.pack(anchor="w")
            rows = [("Last active", fmt_ago(s["now"] - s["last_ts"]) if s["last_ts"] else "—"),
                    ("Today", fmt_metric(mval(s["kpi"]["today"]["agg"], metric), metric))]
            for i, (k, v) in enumerate(rows):
                self.lbl(grid, k, "tiny", "muted").grid(row=i, column=0, sticky="w", pady=px(1))
                self.lbl(grid, v, "small").grid(row=i, column=1, sticky="w", padx=(px(8), 0))

        models = w["models"] if w and w["models"] else s["models_today"]
        if models:
            tk.Frame(body, bg=th["border"], height=1).pack(fill="x", pady=(px(12), px(10)))
            self.composition(body, models, metric, "This window" if w and w["models"] else "Today")

        self.render_limits_card(s)
        self.render_kpis(s)

        body, head = self.card(self.content, "Last 24 hours")
        fams = [fm for fm in FAMS if any(b["fam"].get(fm) for b in s["hourly"])]
        self.legend(head, fams)

        def hour_label(i, b):
            hr = time.localtime(b["start"]).tm_hour
            return f"{hr:02d}" if hr % 6 == 0 and i < 23 else None

        def hour_tip(i):
            b = s["hourly"][i]
            return self.bucket_tip(f"{fmt_clock(b['start'])}–{fmt_clock(b['start'] + 3600)}", b, metric)

        BarChart(self, body, self.CW, px(84), s["hourly"], metric, hour_label, hour_tip, mark_last=True)

    def composition(self, parent, models, metric, scope):
        """One stacked bar of model share + labelled keys (identity never by colour alone)."""
        th, f, px = self.th, self.f, self.px
        total = sum(m["val"] for m in models) or 1.0
        h, gap = px(7), max(1, px(2))
        c = tk.Canvas(parent, width=self.CW, height=h, bg=th["surface"], highlightthickness=0, bd=0)
        c.pack(anchor="w")
        x = 0.0
        shown = [m for m in models if m["val"] / total >= 0.004] or models[:1]
        tot_shown = sum(m["val"] for m in shown) or 1.0
        for i, m in enumerate(shown):
            wd = self.CW * m["val"] / tot_shown
            x2 = x + wd - (gap if i < len(shown) - 1 else 0)
            if x2 - x >= 1:
                c.create_rectangle(x, 0, x2, h, fill=th["series"][m["fam"]], width=0)
            x += wd
        lines = [f"{scope} by model ({METRIC_NAME[metric]})"]
        for m in models:
            a = m["agg"]
            lines.append(f"{m['name']}: {fmt_metric(m['val'], metric)} · {m['val'] / total * 100:.0f}% · "
                         f"{fmt_tokens(tok(a))} tok · {a[5]:,} msgs")
        tip = "\n".join(lines)
        keys = tk.Frame(parent, bg=th["surface"])
        keys.pack(fill="x", pady=(px(6), 0))
        used, row = 0, None
        for m in models[:4]:
            text = f"{m['name']} {fmt_metric(m['val'], metric)} · {m['val'] / total * 100:.0f}%"
            need = f["tiny"].measure(text) + px(22)
            if row is None or used + need > self.CW:
                row = tk.Frame(keys, bg=th["surface"])
                row.pack(fill="x", pady=(0, px(2)))
                used = 0
            self.shape(row, "swatch", th["series"][m["fam"]], 7).pack(side="left", padx=(0 if not used else px(10), px(5)))
            self.lbl(row, text, "tiny", "ink2").pack(side="left")
            used += need
        for w in [c, keys] + keys.winfo_children() + [g for r in keys.winfo_children() for g in r.winfo_children()]:
            w.bind("<Enter>", lambda e: self.tip.show(tip, e.x_root, e.y_root))
            w.bind("<Leave>", lambda e: self.tip.hide())

    def render_limits_card(self, s):
        if not self.cfg["live_limits"] or self.args.no_live:
            return
        th, px = self.th, self.px
        live = s["live"]
        st = live.get("status")
        if st == "off":
            return
        items = live.get("items") or []
        ring_live = s["window"] and s["window"]["src"] == "live"
        rows = [it for it in items if not (ring_live and it["key"] == "five_hour")]
        if st in ("ok", "stale") and rows:
            when = fmt_ago(s["now"] - live.get("fetched", s["now"]))
            right = ("live · " if st == "ok" else "stale · ") + when
            title = "Weekly limits" if all(it["key"].startswith("seven_day") for it in rows) else "Plan limits"
            body, _ = self.card(self.content, title, right)
            for i, it in enumerate(rows):
                sev = severity(it["pct"], th)
                period = WINDOW_SEC if it["key"] == "five_hour" else 7 * 86400
                elapsed = None
                if it["resets"]:
                    elapsed = min(1.0, max(0.0, 1 - (it["resets"] - s["now"]) / period))
                    if sev[0] == "ok" and it["pct"] / 100.0 > elapsed + 0.03 and it["pct"] >= 15:
                        sev = ("warn", STATUS["warn"], "Ahead of pace", "triangle")
                r = tk.Frame(body, bg=th["surface"])
                r.pack(fill="x", pady=(0 if i == 0 else px(9), 0))
                top = tk.Frame(r, bg=th["surface"])
                top.pack(fill="x")
                self.lbl(top, it["label"], "small", "ink2").pack(side="left")
                self.lbl(top, f"{it['pct']:.0f}%", "smallb").pack(side="right")
                if sev[0] != "ok":
                    self.shape(top, sev[3], sev[1], 8).pack(side="right", padx=(0, px(5)))
                bot = tk.Frame(r, bg=th["surface"])
                bot.pack(fill="x", pady=(px(4), 0))
                reset_txt = f"resets {fmt_when(it['resets'], s['now'])}" if it["resets"] else ""
                self.meter(bot, it["pct"] / 100.0, sev[1], width=self.CW - px(104),
                           track=mix(th["surface"], sev[1], 0.2), marker=elapsed,
                           ticks=5 if period == WINDOW_SEC else 7).pack(side="left")
                self.lbl(bot, reset_txt, "tiny", "muted").pack(side="right")
                if it["resets"]:
                    tip = f"{it['label']}: {it['pct']:.0f}% used, {elapsed * 100:.0f}% of the period gone\n" \
                          f"Resets {fmt_when(it['resets'], s['now'])} (in {fmt_dur(it['resets'] - s['now'])})\n" \
                          "White line = time elapsed. Fill past the line = on track to run out early."
                    for w in (r, top, bot) + tuple(top.winfo_children()) + tuple(bot.winfo_children()):
                        w.bind("<Enter>", lambda e, t=tip: self.tip.show(t, e.x_root, e.y_root))
                        w.bind("<Leave>", lambda e: self.tip.hide())
            ex = live.get("extra")
            if ex:
                r = tk.Frame(body, bg=th["surface"])
                r.pack(fill="x", pady=(px(9), 0))
                txt = f"{ex['pct']:.0f}% of monthly cap" if ex.get("pct") is not None else "on"
                self.lbl(r, "Extra usage", "small", "ink2").pack(side="left")
                self.lbl(r, txt, "smallb").pack(side="right")
        elif st in ("ok", "stale"):
            return  # only the 5-hour limit exists and it's already the ring
        else:
            body, _ = self.card(self.content, "Plan limits")
            msg = "Checking your plan limits…" if st == "idle" else (live.get("msg") or "Unavailable.")
            self.lbl(body, msg, "small", "muted", justify="left", wraplength=self.CW).pack(anchor="w")
            if st not in ("idle",):
                self.lbl(body, "Showing estimates from your local logs instead.", "tiny", "muted").pack(anchor="w", pady=(px(2), 0))
            if st == "nobridge":
                self.button(body, "Connect Claude Code", self.connect_statusline, primary=True).pack(anchor="w", pady=(px(10), 0))

    def render_kpis(self, s):
        th, px, metric = self.th, self.px, s["metric"]
        body, _ = self.card(self.content)
        k = s["kpi"]
        for i, (key, label) in enumerate((("today", "Today"), ("7d", "7 days"), ("30d", "30 days"))):
            if i:
                tk.Frame(body, bg=th["border"], width=1).grid(row=0, column=i * 2 - 1, sticky="ns", padx=px(10))
            col = tk.Frame(body, bg=th["surface"])
            col.grid(row=0, column=i * 2, sticky="nw")
            agg = k[key]["agg"]
            self.lbl(col, label, "tiny", "muted").pack(anchor="w")
            self.lbl(col, fmt_metric(mval(agg, metric), metric), "h2").pack(anchor="w")
            second = f"{fmt_tokens(tok(agg))} tok" if metric == "cost" else fmt_cost(agg[4])
            self.lbl(col, second, "tiny", "ink2").pack(anchor="w")
            self.lbl(col, f"{agg[5]:,} msgs", "tiny", "muted").pack(anchor="w")
            tip = f"{label}: {agg[5]:,} messages in {k[key]['sess']} session{'s' if k[key]['sess'] != 1 else ''}\n" \
                  f"{fmt_cost(agg[4])} · in {fmt_tokens(agg[0])} · out {fmt_tokens(agg[1])} · " \
                  f"cache write {fmt_tokens(agg[2])} · cache read {fmt_tokens(agg[3])}"
            for w in [col] + col.winfo_children():
                w.bind("<Enter>", lambda e, t=tip: self.tip.show(t, e.x_root, e.y_root))
                w.bind("<Leave>", lambda e: self.tip.hide())
        body.grid_columnconfigure((0, 2, 4), weight=1, uniform="kpi")
        avg = k["avg_prev7"]
        if avg > 0:
            d = mval(k["today"]["agg"], metric) / avg - 1
            arrow = "▲" if d >= 0 else "▼"
            txt = f"{arrow} Today is {abs(d) * 100:.0f}% {'above' if d >= 0 else 'below'} your 7-day average " \
                  f"({fmt_metric(avg, metric)}/day)"
            self.lbl(body, txt, "tiny", "ink2", wraplength=self.CW).grid(row=1, column=0, columnspan=5, sticky="w",
                                                                         pady=(px(8), 0))

    def bucket_tip(self, title, b, metric):
        agg = b["agg"]
        if not agg[5]:
            return f"{title}\nNo usage"
        lines = [title, f"{fmt_cost(agg[4])} · {fmt_tokens(tok(agg))} tokens · {agg[5]:,} msgs"]
        parts = sorted(((v, fm) for fm, v in b["fam"].items() if v > 0), reverse=True)
        if len(parts) > 1:
            lines.append(" · ".join(f"{FAM_LABEL[fm]} {fmt_metric(v, metric)}" for v, fm in parts[:3]))
        elif parts:
            lines.append(FAM_LABEL[parts[0][1]] + " only")
        return "\n".join(lines)

    # ---------------------------------------------------------------- history
    def render_history(self, s):
        th, px = self.th, self.px
        if self.no_data(s):
            return
        metric, n = s["metric"], self.cfg["hist_range"]
        top = tk.Frame(self.content, bg=th["bg"])
        top.pack(fill="x", pady=(0, px(8)))
        self.segmented(top, [(7, "7 days"), (14, "14 days"), (30, "30 days")], n,
                       lambda k: self.set_cfg("hist_range", k)).pack(side="left")
        self.button(top, "Export CSV", self.export_csv).pack(side="right")

        days = s["daily"][-n:]
        body, head = self.card(self.content, "Daily usage")
        self.legend(head, [fm for fm in FAMS if any(b["fam"].get(fm) for b in days)])

        def day_lbl(i, b):
            d = date.fromordinal(b["day"])
            if n == 7:
                return WEEKDAYS[d.weekday()]
            step = 2 if n == 14 else 5
            if (len(days) - 1 - i) % step:
                return None
            return f"{d.day} {MONTHS[d.month - 1]}" if i < step else str(d.day)

        def day_tip(i):
            b = days[i]
            return self.bucket_tip(day_label(b["day"], s["today"]), b, metric)

        BarChart(self, body, self.CW, px(112), days, metric, day_lbl, day_tip, mark_last=True)
        vals = [sum(b["fam"].values()) for b in days]
        total = sum(vals)
        if total > 0:
            peak_i = max(range(len(vals)), key=lambda i: vals[i])
            active_days = sum(1 for v in vals if v > 0)
            txt = (f"Total {fmt_metric(total, metric)} · {fmt_metric(total / n, metric)}/day avg · "
                   f"busiest {fmt_date(days[peak_i]['day'])} ({fmt_metric(vals[peak_i], metric)}) · "
                   f"{active_days}/{n} days active")
            self.lbl(body, txt, "tiny", "ink2", justify="left", wraplength=self.CW).pack(anchor="w", pady=(px(8), 0))

        body, head = self.card(self.content, "When you use Claude")
        cell, tf = px(9), self.f["tiny"]
        x0 = tf.measure("less") + px(5)
        lw = x0 + 5 * (cell + 1) + px(4) + tf.measure("more") + 2
        lg = tk.Canvas(head, width=lw, height=max(cell + 2, tf.metrics("linespace")), bg=th["surface"],
                       highlightthickness=0, bd=0)
        lg.pack(side="right")
        mid = int(lg["height"]) / 2.0
        lg.create_text(0, mid, text="less", anchor="w", font=tf, fill=th["muted"])
        for i in range(5):
            lg.create_rectangle(x0 + i * (cell + 1), mid - cell / 2.0, x0 + i * (cell + 1) + cell - 1, mid + cell / 2.0,
                                fill=ramp(th["heat"], i / 4.0), width=0)
        lg.create_text(x0 + 5 * (cell + 1) + px(4), mid, text="more", anchor="w", font=tf, fill=th["muted"])
        Heatmap(self, body, self.CW, s)
        self.lbl(body, "Last 30 days, by weekday and hour.", "tiny", "muted").pack(anchor="w", pady=(px(6), 0))

        blocks = s["blocks"]
        if blocks:
            ref = s["limit"] or max(b["val"] for b in blocks) or 1.0
            right = {"custom": "vs your limit", "auto": "vs your record"}.get(s["limit_src"], "")
            body, _ = self.card(self.content, "Recent 5-hour windows", right)
            for i, b in enumerate(blocks[:5]):
                frac = b["val"] / ref if ref else 0
                sev = severity(frac * 100, th)
                r = tk.Frame(body, bg=th["surface"])
                r.pack(fill="x", pady=(0 if i == 0 else px(8), 0))
                top = tk.Frame(r, bg=th["surface"])
                top.pack(fill="x")
                d = day_label(local_day(b["start"]), s["today"])
                self.lbl(top, f"{d}  {fmt_clock(b['start'])}–{fmt_clock(b['end'])}", "small").pack(side="left")
                if b["active"]:
                    self.lbl(top, " NOW ", "tinyb", th["accent"], bg=th["accent_soft"]).pack(side="left", padx=px(6))
                elif b["is_record"]:
                    self.lbl(top, " RECORD ", "tinyb", "ink2", bg=th["raised"]).pack(side="left", padx=px(6))
                self.lbl(top, fmt_metric(b["val"], metric), "smallb").pack(side="right")
                mrow = tk.Frame(r, bg=th["surface"])
                mrow.pack(fill="x", pady=(px(4), 0))
                pct_txt = f"{frac * 100:.0f}%"
                self.lbl(mrow, f"{b['agg'][5]:,} msgs · {pct_txt}", "tiny", "muted").pack(side="right")
                self.meter(mrow, frac, sev[1] if s["limit"] else th["accent"], width=self.CW - px(96), height=5).pack(side="left")

    # ---------------------------------------------------------------- projects
    def render_projects(self, s):
        th, px = self.th, self.px
        if self.no_data(s):
            return
        metric, rk = s["metric"], self.cfg["proj_range"]
        top = tk.Frame(self.content, bg=th["bg"])
        top.pack(fill="x", pady=(0, px(8)))
        self.segmented(top, [("today", "Today"), ("7d", "7 days"), ("30d", "30 days")], rk,
                       lambda k: self.set_cfg("proj_range", k)).pack(side="left")
        rows = s["projects"][rk]
        if not rows:
            self.empty_card("No activity in this period", "Try a longer range.")
            return
        total = sum(p["val"] for p in rows) or 1.0
        body, _ = self.card(self.content, f"{len(rows)} project{'s' if len(rows) != 1 else ''}",
                            f"{fmt_metric(total, metric)} total")
        mx = rows[0]["val"] or 1.0
        for i, p in enumerate(rows[:8]):
            r = tk.Frame(body, bg=th["surface"])
            r.pack(fill="x", pady=(0 if i == 0 else px(9), 0))
            t = tk.Frame(r, bg=th["surface"])
            t.pack(fill="x")
            name = self.elide(p["name"], self.f["bodyb"], self.CW - px(120))
            self.lbl(t, name, "bodyb").pack(side="left")
            self.lbl(t, f"{p['val'] / total * 100:.0f}%", "tiny", "muted").pack(side="right", padx=(px(6), 0))
            self.lbl(t, fmt_metric(p["val"], metric), "smallb").pack(side="right")
            self.meter(r, p["val"] / mx, th["accent"], height=5).pack(anchor="w", pady=(px(4), px(3)))
            second = f"{fmt_tokens(tok(p['agg']))} tok" if metric == "cost" else fmt_cost(p["agg"][4])
            info = (f"{second} · {p['agg'][5]:,} msgs · {p['sess']} session{'s' if p['sess'] != 1 else ''} · "
                    f"active {fmt_ago(s['now'] - p['last'])}")
            self.lbl(r, self.elide(info, self.f["tiny"], self.CW), "tiny", "muted").pack(anchor="w")
        if len(rows) > 8:
            rest = sum(p["val"] for p in rows[8:])
            self.lbl(body, f"+ {len(rows) - 8} more · {fmt_metric(rest, metric)}", "tiny", "muted").pack(anchor="w", pady=(px(8), 0))

    # ---------------------------------------------------------------- sessions
    def render_sessions(self, s):
        th, px = self.th, self.px
        if self.no_data(s):
            return
        metric, sess = s["metric"], s["sessions"]
        body, _ = self.card(self.content, "Recent sessions",
                            f"{s['n_sessions']:,} in {self.cfg['history_days']} days")
        for i, x in enumerate(sess[:9]):
            r = tk.Frame(body, bg=th["surface"])
            r.pack(fill="x", pady=(0 if i == 0 else px(9), 0))
            t = tk.Frame(r, bg=th["surface"])
            t.pack(fill="x")
            if x["live"]:
                self.lbl(t, " LIVE ", "tinyb", th["accent"], bg=th["accent_soft"]).pack(side="left", padx=(0, px(6)))
            self.lbl(t, self.elide(x["project"], self.f["bodyb"], self.CW - px(150)), "bodyb").pack(side="left")
            self.lbl(t, fmt_metric(x["val"], metric), "smallb").pack(side="right")
            if x.get("cc_cost") and metric == "cost" and x["cc_cost"] > x["val"] * 1.02:
                self.lbl(t, f"CC {fmt_cost(x['cc_cost'])}", "tiny", "muted").pack(side="right", padx=(0, px(6)))
            b = tk.Frame(r, bg=th["surface"])
            b.pack(fill="x", pady=(px(3), 0))
            self.shape(b, "swatch", th["series"][x["fam"]], 7).pack(side="left", padx=(0, px(5)))
            model = x["model"] + (f" +{x['n_models'] - 1}" if x["n_models"] > 1 else "")
            dur = fmt_dur(x["last"] - x["first"])
            when = day_label(local_day(x["first"]), s["today"])
            when = fmt_clock(x["first"]) if when == "Today" else f"{when} {fmt_clock(x['first'])}"
            second = f"{fmt_tokens(tok(x['agg']))} tok" if metric == "cost" else fmt_cost(x["agg"][4])
            info = self.elide(f"{model} · {when} · {dur} · {x['agg'][5]:,} msgs · {second}", self.f["tiny"],
                              self.CW - px(16))
            self.lbl(b, info, "tiny", "muted").pack(side="left")

    # ---------------------------------------------------------------- mini & banner
    def render_mini(self, s):
        th, px = self.th, self.px
        size = px(36)
        if s is None:
            self.draw_ring(self.mini_ring, size, 0, th["muted"], None, thick=px(5))
            self.mini_top.configure(text="Loading…")
            self.mini_sub.configure(text="reading logs")
            return
        w, g, metric = s["window"], s["gauge"], s["metric"]
        pct = g["pct"] if w else None
        sev = severity(pct, th)
        self.draw_ring(self.mini_ring, size, (pct or 0) / 100.0, sev[1], None, thick=px(5))
        if w:
            val = fmt_metric(w["val"], metric)
            self.mini_top.configure(text=f"{pct:.0f}%  ·  {val}" if pct is not None else val)
            sub = f"limit ~{fmt_clock(g['eta'])}" if g["eta"] else f"resets in {fmt_dur(w['remaining'])}"
            self.mini_sub.configure(text=sub)
        else:
            self.mini_top.configure(text="Idle")
            self.mini_sub.configure(text="today " + fmt_metric(mval(s["kpi"]["today"]["agg"], metric), metric))

    def render_banner(self):
        for w in self.banner_slot.winfo_children():
            w.destroy()
        b = self.banner
        if not b or time.time() - b[2] > 1800:
            return
        th, px = self.th, self.px
        col = STATUS["crit"] if b[0] >= 90 else (STATUS["warn"] if b[0] > 0 else th["accent"])
        bg = mix(th["surface"], col, 0.16)
        fr = tk.Frame(self.banner_slot, bg=bg)
        fr.pack(fill="x", padx=px(12), pady=(0, px(8)))
        self.shape(fr, "triangle" if b[0] else "dot", col, 9).pack(side="left", padx=(px(10), px(7)), pady=px(8))
        tk.Label(fr, text=b[1], font=self.f["small"], fg=th["ink"], bg=bg, anchor="w", justify="left",
                 wraplength=self.CW - px(40)).pack(side="left", fill="x", expand=True)
        x = tk.Label(fr, text="×", font=self.f["bodyb"], fg=th["ink2"], bg=bg, cursor="hand2")
        x.pack(side="right", padx=px(10))
        x.bind("<Button-1>", lambda e: (setattr(self, "banner", None), self.render_banner()))

    @staticmethod
    def elide(text, font, maxw):
        if font.measure(text) <= maxw:
            return text
        while text and font.measure(text + "…") > maxw:
            text = text[:-1]
        return text + "…"

    # ---------------------------------------------------------------- alerts
    def check_alerts(self, s):
        if not s:
            return
        cfg, now = self.cfg, s["now"]
        quiet = alerts_quiet(cfg, now)
        events = plan_alerts(cfg, s, cfg.setdefault("alerted", {}), now)
        for ev in events:
            self.raise_alert(ev, quiet)
            self.run_hook("on_alert_command", ev["kind"], ev["label"], ev["pct"])
        if events:
            self.save_soon()
        w, g = s["window"], s["gauge"]
        key = "w%d" % int(w["end"]) if w else None
        pct = (g["pct"] or 0) if w else 0
        pw = self.prev_win
        levels = alert_levels_for(cfg, "session")
        if (cfg.get("alerts") and pw and pw["key"] and pw["key"] != key and cfg.get("notify_reset") and levels
                and pw["max"] >= levels[0]):
            ev = {"kind": "reset", "scope": "session", "level": 0, "pct": 0, "label": "5-hour window",
                  "text": "Your 5-hour window has reset. Full capacity is back.", "title": "Window reset"}
            self.raise_alert(ev, quiet)
            self.run_hook("on_reset_command", "reset", "5-hour window", 0)
        self.prev_win = {"key": key, "max": max(pct, pw["max"] if pw and pw["key"] == key else 0)}

    def snooze(self, minutes):
        self.cfg["snooze_until"] = time.time() + minutes * 60 if minutes else 0.0
        self.save_soon()
        self.toast = (f"Alerts snoozed for {minutes // 60 if minutes % 60 == 0 else minutes} "
                      f"{'hour' if minutes == 60 else 'hours' if minutes % 60 == 0 else 'min'}" if minutes
                      else "Alerts resumed", time.time() + 5)
        self.update_footer()

    def run_hook(self, key, event, label, pct):
        cmd = str(self.cfg.get(key) or "").strip()
        if not cmd or self.args.demo:
            return
        env = dict(os.environ, LIMITLINE_EVENT=event, LIMITLINE_LABEL=label, LIMITLINE_PCT=f"{pct:.0f}")
        try:
            subprocess.Popen(cmd, shell=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    def raise_alert(self, ev, quiet=False):
        level = ev["level"]
        self.banner = (level, ev["text"], time.time())
        col = STATUS["crit"] if level >= 90 else (STATUS["warn"] if level else self.th["accent"])
        if not self.cfg["mini"]:
            self.render_banner()
        if quiet:
            return      # snoozed or quiet hours: the banner is the only trace
        self.flash(col, 8)
        if self.cfg.get("desktop_notify"):
            notify_desktop(ev["title"], ev["text"])
        if self.cfg.get("alert_sound"):
            beep(self.root)
        self.mascot.event(ev)

    def flash(self, color, n):
        if n <= 0 or not self.root.winfo_exists():
            self.root.configure(bg=self.th["border"])
            return
        self.root.configure(bg=color if n % 2 == 0 else self.th["border"])
        self.root.after(260, lambda: self.flash(color, n - 1))

    # ---------------------------------------------------------------- actions
    def export_csv(self):
        s = self.snap
        if not s or not s["daily_models"]:
            self.flash_toast("Nothing to export yet")
            return
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv",
                                            initialfile=f"limitline-{date.today().isoformat()}.csv",
                                            filetypes=[("CSV file", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                wr = csv.writer(fh)
                wr.writerow(["date", "model", "messages", "input_tokens", "output_tokens", "cache_write_tokens",
                             "cache_read_tokens", "total_tokens", "api_equivalent_cost_usd"])
                for (day, model), a in sorted(s["daily_models"].items()):
                    wr.writerow([date.fromordinal(day).isoformat(), model, a[5], a[0], a[1], a[2], a[3], tok(a),
                                 f"{a[4]:.4f}"])
            self.flash_toast("Saved " + os.path.basename(path), 4)
        except OSError as ex:
            self.flash_toast(f"Couldn't save: {ex.strerror}", 5)

    def open_logs(self):
        roots = (self.snap or {}).get("scan", {}).get("roots") or log_roots(self.cfg.get("extra_paths"))
        open_path(roots[0] if roots else HOME)

    def open_welcome(self):
        if getattr(self, "welcome", None) and self.welcome.win.winfo_exists():
            self.welcome.win.lift()
            return
        self.welcome = Welcome(self)

    def connect_statusline(self):
        ok, msg = install_statusline(self.args.config_dir)
        self.toast = (msg, time.time() + 9)
        self.update_footer()
        self.live.wake.set()
        return ok, msg

    def open_settings(self):
        if self.settings and self.settings.win.winfo_exists():
            self.settings.win.lift()
            self.settings.win.focus_force()
            return
        self.settings = SettingsDialog(self)

    def apply_settings(self, old):
        cfg = self.cfg
        self.topmost_var.set(cfg["topmost"])
        self.apply_window_attrs()
        if cfg["theme"] != old["theme"] or cfg["accent"] != old["accent"]:
            self._rings.clear()
            self.build()
            if IS_WIN:
                self.root.after(60, self.win_tweaks)
        else:
            self.pin_btn.set_active(cfg["topmost"])
        if cfg["extra_paths"] != old["extra_paths"] or cfg["history_days"] != old["history_days"]:
            self.worker.reset = True
        if cfg["live_limits"] != old["live_limits"] or cfg["live_oauth"] != old["live_oauth"]:
            self.live.wake.set()
        self.worker.wake.set()
        self.save_soon()
        self.render()

    def quit(self):
        try:
            if not self.cfg["mini"] or self.cfg.get("x") is None:
                self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
            if self.persist:
                save_config(self.cfg)
        finally:
            self.root.destroy()


# =============================================================================
# Charts
# =============================================================================
class BarChart:
    """Stacked columns by model family with a per-column hover tooltip."""

    def __init__(self, app, parent, width, height, buckets, metric, xlabel, tipfn, mark_last=False):
        self.app, self.buckets, self.tipfn, self.hi = app, buckets, tipfn, None
        th, f, px = app.th, app.f, app.px
        c = self.c = tk.Canvas(parent, width=width, height=height, bg=th["surface"], highlightthickness=0, bd=0)
        c.pack(anchor="w")
        totals = [sum(b["fam"].values()) for b in buckets]
        mx = max(totals) if totals else 0.0
        step, top = nice_scale(mx)
        ticks = [step * i for i in range(1, int(round(top / step)) + 1)] if mx > 0 else []
        labels = [fmt_axis(t, metric) for t in ticks]
        lw = max([f["tiny"].measure(t) for t in labels] + [px(10)]) + px(7)
        self.x0, self.x1, self.y0, self.y1 = lw, width - 1, px(6), height - px(16)
        ph = self.y1 - self.y0
        for t, lab in zip(ticks, labels):
            y = self.y1 - t / top * ph
            c.create_line(self.x0, y, self.x1, y, fill=th["grid"])
            c.create_text(self.x0 - px(6), y, text=lab, anchor="e", font=f["tiny"], fill=th["muted"])
        c.create_line(self.x0, self.y1, self.x1, self.y1, fill=th["base"])
        n = len(buckets)
        self.slot = (self.x1 - self.x0) / max(1, n)
        bw = max(2.0, min(px(22), self.slot * 0.68))
        gap = max(1.0, px(1.5))
        for i, b in enumerate(buckets):
            cx = self.x0 + (i + 0.5) * self.slot
            xa, xb = cx - bw / 2.0, cx + bw / 2.0
            segs = [(fm, b["fam"].get(fm, 0.0)) for fm in FAMS if b["fam"].get(fm, 0.0) > 0]
            y = self.y1
            for j, (fm, v) in enumerate(segs):
                hgt = v / top * ph
                ya = y - hgt
                if j == len(segs) - 1:
                    top_rounded(c, xa, min(ya, y - 1), xb, y, px(3), fill=th["series"][fm])
                elif hgt > gap + 0.5:
                    c.create_rectangle(xa, ya + gap, xb, y, fill=th["series"][fm], width=0)
                y = ya
            lab = xlabel(i, b)
            if mark_last and i == n - 1:
                txt = lab or "now"
                half = f["tinyb"].measure(txt) / 2.0
                tx = min(cx, self.x1 - half - 1)
                c.create_text(tx, self.y1 + px(3), text=txt, anchor="n", font=f["tinyb"], fill=th["accent"])
            elif lab and not (mark_last and (n - 1 - i) * self.slot < px(24)):
                c.create_text(cx, self.y1 + px(3), text=lab, anchor="n", font=f["tiny"], fill=th["muted"])
        if mx <= 0:
            c.create_text((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2, text="No usage in this period",
                          font=f["small"], fill=th["muted"])
        c.bind("<Motion>", self.motion)
        c.bind("<Leave>", self.leave)

    def motion(self, e):
        n = len(self.buckets)
        if not n or e.x < self.x0 or e.x > self.x1:
            return self.leave()
        i = max(0, min(n - 1, int((e.x - self.x0) / self.slot)))
        if i != self.hi:
            self.hi = i
            self.c.delete("hover")
            x = self.x0 + i * self.slot
            self.c.create_rectangle(x + 1, self.y0 - 2, x + self.slot - 1, self.y1, fill=self.app.th["hover"],
                                    width=0, tags="hover")
            self.c.tag_lower("hover")
        self.app.tip.show(self.tipfn(i), e.x_root, e.y_root)

    def leave(self, _e=None):
        self.hi = None
        self.c.delete("hover")
        self.app.tip.hide()


class Heatmap:
    """Weekday x hour activity grid (single-hue sequential ramp, sqrt-scaled)."""

    def __init__(self, app, parent, width, s):
        self.app, self.s = app, s
        th, f, px = app.th, app.f, app.px
        self.lw = max(f["tiny"].measure(d) for d in WEEKDAYS) + px(8)
        self.cw = (width - self.lw) / 24.0
        self.ch = px(13)
        gap = max(1, px(2))
        height = 7 * self.ch + px(14)
        c = self.c = tk.Canvas(parent, width=width, height=height, bg=th["surface"], highlightthickness=0, bd=0)
        c.pack(anchor="w")
        mx = s["heat_max"]
        for d in range(7):
            y = d * self.ch
            c.create_text(self.lw - px(7), y + (self.ch - gap) / 2.0, text=WEEKDAYS[d], anchor="e",
                          font=f["tiny"], fill=th["muted"])
            for h in range(24):
                v = s["heat"][d][h]
                x = self.lw + h * self.cw
                col = th["grid"] if v <= 0 or mx <= 0 else ramp(th["heat"], math.sqrt(v / mx))
                c.create_rectangle(x, y, x + self.cw - gap, y + self.ch - gap, fill=col, width=0)
        for h in (0, 6, 12, 18):
            c.create_text(self.lw + h * self.cw, 7 * self.ch + px(1), text=f"{h:02d}:00", anchor="nw",
                          font=f["tiny"], fill=th["muted"])
        c.bind("<Motion>", self.motion)
        c.bind("<Leave>", self.leave)

    def motion(self, e):
        h, d = int((e.x - self.lw) // self.cw), int(e.y // self.ch)
        if not (0 <= h < 24 and 0 <= d < 7):
            return self.leave()
        th, s = self.app.th, self.s
        self.c.delete("hover")
        x, y = self.lw + h * self.cw, d * self.ch
        gap = max(1, self.app.px(2))
        self.c.create_rectangle(x - 1, y - 1, x + self.cw - gap + 1, y + self.ch - gap + 1, outline=th["ink"],
                                width=1, tags="hover")
        v, n = s["heat"][d][h], s["heat_n"][d][h]
        day = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"][d]
        body = f"{fmt_metric(v, s['metric'])} · {n:,} msgs" if n else "No usage"
        self.app.tip.show(f"{day} {h:02d}:00–{(h + 1) % 24:02d}:00\n{body} (last 30 days)", e.x_root, e.y_root)

    def leave(self, _e=None):
        self.c.delete("hover")
        self.app.tip.hide()


# =============================================================================
# Settings dialog
# =============================================================================
class Switch(_Canvas):
    def __init__(self, parent, app, value, command):
        self.app, self.value, self.command = app, bool(value), command
        self.w, self.h = app.px(34), app.px(18)
        super().__init__(parent, width=self.w, height=self.h, bg=parent["bg"], highlightthickness=0, bd=0,
                         cursor="hand2")
        self.bind("<ButtonRelease-1>", self._toggle)
        self.draw()

    def _toggle(self, _e):
        self.value = not self.value
        self.draw()
        self.command(self.value)

    def draw(self):
        app, th, w, h = self.app, self.app.th, self.w, self.h
        bg = self["bg"]
        track = th["accent"] if self.value else th["base"]
        r = h / 2.0 - app.px(3)
        cx = (w - h / 2.0) if self.value else h / 2.0
        key = ("switch", w, h, self.value, track, bg)
        im = app.img(key, w, h, bg, lambda: [
            g_rrect(0, 0, w, h, h / 2.0, track),
            g_disc(cx, h / 2.0 + 0.6, r + 0.6, mix(track, "#000000", 0.35)),
            g_disc(cx, h / 2.0, r, "#ffffff")])
        self.delete("all")
        self.create_image(0, 0, image=im, anchor="nw")


class Slider(_Canvas):
    def __init__(self, parent, app, value, lo, hi, command, length):
        self.app, self.value, self.lo, self.hi, self.command = app, value, lo, hi, command
        self.L, self.H = length, app.px(18)
        super().__init__(parent, width=length, height=self.H, bg=parent["bg"], highlightthickness=0, bd=0,
                         cursor="hand2")
        self.bind("<Button-1>", self._set)
        self.bind("<B1-Motion>", self._set)
        self.draw()

    def _set(self, e):
        r = self.H / 2.0
        frac = max(0.0, min(1.0, (e.x - r) / max(1.0, self.L - 2 * r)))
        v = int(round(self.lo + frac * (self.hi - self.lo)))
        if v != self.value:
            self.value = v
            self.draw()
            self.command(v)

    def draw(self):
        app, th, px = self.app, self.app.th, self.app.px
        bg = self["bg"]
        r = self.H / 2.0
        x0, x1 = r, self.L - r
        xv = x0 + (x1 - x0) * (self.value - self.lo) / float(self.hi - self.lo)
        t, k = px(4) / 2.0, r - px(3)
        key = ("slider", self.L, self.H, round(xv, 1), th["accent"], th["base"], bg)
        im = app.img(key, self.L, self.H, bg, lambda: [
            g_rrect(x0 - t, r - t, x1 + t, r + t, t, th["base"]),
            g_rrect(x0 - t, r - t, xv, r + t, t, th["accent"]),
            g_disc(xv, r + 0.6, k + 0.8, mix(bg, "#000000", 0.35)),
            g_disc(xv, r, k + 0.6, th["border"]), g_disc(xv, r, k, "#ffffff")])
        self.delete("all")
        self.create_image(0, 0, image=im, anchor="nw")


class SettingsDialog:
    def __init__(self, app):
        self.app = app
        cfg = app.cfg
        self.v = {k: (list(v) if isinstance(v, list) else v) for k, v in cfg.items() if k != "alerted"}
        self.auto = autostart_enabled()
        self.orig_alpha = cfg["opacity"]
        self.vars = {
            "limit": tk.StringVar(value=self._limit_text(cfg["limit_value"], cfg["metric"])),
            "refresh": tk.StringVar(value=str(cfg["refresh_sec"])),
            "levels": tk.StringVar(value=", ".join(str(x) for x in cfg["alert_levels"])),
            "levels_week": tk.StringVar(value=", ".join(str(x) for x in cfg["alert_levels_week"])),
            "step": tk.StringVar(value=str(cfg["alert_step"] or "")),
            "qfrom": tk.StringVar(value=cfg["quiet_from"]),
            "qto": tk.StringVar(value=cfg["quiet_to"]),
            "extra": tk.StringVar(value=(cfg["extra_paths"] or [""])[0]),
            "hook": tk.StringVar(value=cfg.get("on_alert_command") or ""),
            "opacity": tk.IntVar(value=int(round(cfg["opacity"] * 100))),
        }
        th = app.th
        self.win = tk.Toplevel(app.root)
        self.win.title(f"Settings · {APP_NAME}")
        self.win.configure(bg=th["bg"])
        self.win.resizable(False, False)
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        # Save/Cancel stay pinned; the rest scrolls when the screen is too short (small laptops, high DPI)
        self.footbar = tk.Frame(self.win, bg=th["bg"])
        self.footbar.pack(side="bottom", fill="x", padx=app.px(16), pady=(app.px(6), app.px(14)))
        self.canvas = tk.Canvas(self.win, bg=th["bg"], highlightthickness=0, bd=0)
        self.canvas.pack(side="top", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=th["bg"])
        self.canvas.create_window(app.px(16), app.px(14), window=self.body, anchor="nw")
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.win.bind(seq, self._wheel)
        self.build()
        self.fit()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        x0, y0, x1, y1 = app.screen_bounds()
        rx, ry = app.root.winfo_x(), app.root.winfo_y()
        x = rx - w - app.px(12) if rx - w - app.px(12) > x0 else min(x1 - w - app.px(12), rx + app.px(40))
        y = max(y0 + app.px(20), min(ry, y1 - h - app.px(60)))
        self.win.geometry(f"+{int(x)}+{int(y)}")
        self.win.bind("<Escape>", lambda e: self.cancel())
        self.win.bind("<Return>", lambda e: self.save())
        self.win.protocol("WM_DELETE_WINDOW", self.cancel)
        self.win.focus_force()

    def fit(self):
        """Size the scroll area: everything visible if it fits, otherwise cap to the screen and scroll."""
        app = self.app
        self.win.update_idletasks()
        bw, bh = self.body.winfo_reqwidth(), self.body.winfo_reqheight()
        sx0, sy0, sx1, sy1 = app.screen_bounds()
        room = (sy1 - sy0) - app.px(110) - self.footbar.winfo_reqheight()
        ch = min(bh + app.px(14), max(app.px(240), room))
        self.scrolls = bh + app.px(14) > ch
        self.canvas.configure(width=bw + app.px(32), height=ch, scrollregion=(0, 0, bw + app.px(32), bh + app.px(28)))
        self.canvas.yview_moveto(0)

    def _wheel(self, e):
        if not getattr(self, "scrolls", False):
            return
        num = getattr(e, "num", None)
        d = -1 if num == 4 else 1 if num == 5 else (-1 if e.delta > 0 else 1)
        self.canvas.yview_scroll(d * 2, "units")

    @staticmethod
    def _limit_text(value, metric):
        if not value:
            return ""
        return f"{value:g}" if metric == "cost" else fmt_tokens(value)

    # ---- layout helpers
    def section(self, parent, title):
        th, app = self.app.th, self.app
        tk.Label(parent, text=title.upper(), font=app.f["label"], fg=th["muted"], bg=th["bg"]).pack(
            anchor="w", pady=(app.px(10), app.px(5)))
        outer = tk.Frame(parent, bg=th["border"], bd=0, highlightthickness=0)
        outer.pack(fill="x")
        box = tk.Frame(outer, bg=th["surface"], bd=0, highlightthickness=0)
        box.pack(fill="x", padx=1, pady=1)
        box.n = 0
        app.round_corners(outer, th["bg"], app.px(11))
        return box

    def row(self, box, label, make, desc=None):
        th, app, px = self.app.th, self.app, self.app.px
        if box.n:
            tk.Frame(box, bg=th["border"], height=1).pack(fill="x", padx=px(12))
        box.n += 1
        r = tk.Frame(box, bg=th["surface"])
        r.pack(fill="x", padx=px(12), pady=px(8))
        left = tk.Frame(r, bg=th["surface"])
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=label, font=app.f["body"], fg=th["ink"], bg=th["surface"], anchor="w").pack(anchor="w")
        if desc:
            tk.Label(left, text=desc, font=app.f["tiny"], fg=th["muted"], bg=th["surface"], anchor="w",
                     justify="left", wraplength=px(170)).pack(anchor="w")
        make(r).pack(side="right", anchor="e", padx=(px(10), 0))

    def seg(self, key, options, rebuild=False):
        def make(parent):
            def pick(k):
                self.v[key] = k
                if key == "metric":
                    self.vars["limit"].set("")
                self.build()
            return self.app.segmented(parent, options, self.v[key], pick)
        return make

    def switch(self, key):
        def make(parent):
            def setv(val):
                if key == "_autostart":
                    self.auto = val
                else:
                    self.v[key] = val
            return Switch(parent, self.app, self.auto if key == "_autostart" else self.v[key], setv)
        return make

    def entry(self, var, width=8, state="normal"):
        def make(parent):
            th = self.app.th
            return tk.Entry(parent, textvariable=self.vars[var], width=width, font=self.app.f["body"],
                            bg=th["seg_bg"], fg=th["ink"], insertbackground=th["ink"], relief="flat",
                            disabledbackground=th["raised"], disabledforeground=th["muted"],
                            highlightthickness=1, highlightbackground=th["border"], highlightcolor=th["accent"],
                            state=state)
        return make

    # ---- content
    def build(self):
        app, th, f, px = self.app, self.app.th, self.app.f, self.app.px
        for w in self.body.winfo_children():
            w.destroy()
        head = tk.Frame(self.body, bg=th["bg"])
        head.pack(fill="x")
        tk.Label(head, text="Settings", font=f["h2"], fg=th["ink"], bg=th["bg"]).pack(side="left")
        tk.Label(head, text=f"{APP_NAME} {VERSION}", font=f["tiny"], fg=th["muted"], bg=th["bg"]).pack(side="right")
        cols = tk.Frame(self.body, bg=th["bg"])
        cols.pack(fill="both")
        left = tk.Frame(cols, bg=th["bg"], width=px(350))
        left.pack(side="left", fill="y", anchor="n")
        right = tk.Frame(cols, bg=th["bg"], width=px(350))
        right.pack(side="left", fill="y", anchor="n", padx=(px(14), 0))

        box = self.section(left, "Display")
        self.row(box, "Theme", self.seg("theme", [("dark", "Dark"), ("light", "Light")]))
        self.row(box, "Accent", self.seg("accent", [("gold", "Gold"), ("claude", "Clay"), ("ocean", "Ocean"),
                                                    ("forest", "Forest"), ("violet", "Violet")]))

        def opacity(parent):
            fr = tk.Frame(parent, bg=th["surface"])
            val = tk.Label(fr, text=f"{self.vars['opacity'].get()}%", font=f["small"], fg=th["ink2"],
                           bg=th["surface"], width=4, anchor="e")

            def changed(v):
                self.vars["opacity"].set(v)
                val.configure(text=f"{v}%")
                try:
                    app.root.attributes("-alpha", v / 100.0)
                except tk.TclError:
                    pass
            Slider(fr, app, self.vars["opacity"].get(), 40, 100, changed, px(130)).pack(side="left")
            val.pack(side="left", padx=(px(4), 0))
            return fr
        self.row(box, "Opacity", opacity)
        self.row(box, "Always on top", self.switch("topmost"))
        self.row(box, "Borderless window", self.switch("frameless"), "Off = use the system title bar")
        self.row(box, "Launch at login", self.switch("_autostart"))

        box = self.section(left, "Tracking")
        self.row(box, "Main measure", self.seg("metric", [("cost", "Cost"), ("tokens", "Tokens"), ("io", "In+out")]),
                 "Cost is the API-equivalent price of what you used")

        def limit(parent):
            fr = tk.Frame(parent, bg=th["surface"])
            self.app.segmented(fr, [("auto", "Auto"), ("custom", "Custom")], self.v["limit_mode"],
                               lambda k: (self.v.__setitem__("limit_mode", k), self.build())).pack(side="left")
            if self.v["limit_mode"] == "custom":
                unit = "$" if self.v["metric"] == "cost" else "tok"
                self.entry("limit", 7)(fr).pack(side="left", padx=(px(8), px(4)), ipady=px(2))
                tk.Label(fr, text=unit, font=f["small"], fg=th["muted"], bg=th["surface"]).pack(side="left")
            return fr
        self.row(box, "5-hour limit", limit,
                 "Used when live plan limits aren't available. Auto = your busiest past window")

        def refresh(parent):
            fr = tk.Frame(parent, bg=th["surface"])
            self.entry("refresh", 4)(fr).pack(side="left", ipady=px(2))
            tk.Label(fr, text="sec", font=f["small"], fg=th["muted"], bg=th["surface"]).pack(side="left", padx=(px(4), 0))
            return fr
        self.row(box, "Rescan logs every", refresh)
        self.row(box, "History kept", self.seg("history_days", [(30, "30d"), (60, "60d"), (90, "90d")]))

        box = self.section(right, "Alerts")
        self.row(box, "Usage alerts", self.switch("alerts"), "Banner + border flash")

        def levels(parent):
            fr = tk.Frame(parent, bg=th["surface"])
            self.entry("levels", 9)(fr).pack(side="left", ipady=px(2))
            tk.Label(fr, text="%", font=f["small"], fg=th["muted"], bg=th["surface"]).pack(side="left", padx=(px(4), 0))
            return fr
        self.row(box, "5-hour alerts at", levels, "Comma-separated, e.g. 75, 90")

        def pct_entry(var, hint):
            def make(parent):
                fr = tk.Frame(parent, bg=th["surface"])
                self.entry(var, 9)(fr).pack(side="left", ipady=px(2))
                tk.Label(fr, text=hint, font=f["small"], fg=th["muted"], bg=th["surface"]).pack(side="left", padx=(px(4), 0))
                return fr
            return make
        self.row(box, "Weekly alerts at", pct_entry("levels_week", "%"), "Applies to the weekly limits")
        self.row(box, "Also every", pct_entry("step", "%"), "e.g. 25 gives 25, 50, 75, 100. Empty = off")
        self.row(box, "Pace warning", self.switch("alert_forecast"), "Warn when you're on course to run out early")
        self.row(box, "Only when ahead of pace", self.switch("alerts_pace_only"),
                 "Skip alerts while usage is behind the clock")
        self.row(box, "Mascot", self.seg("mascot", [("off", "Off"), ("subtle", "Subtle"), ("full", "Every alert")]),
                 "Subtle: only at 75%+, pace warnings and resets")
        self.row(box, "Animate mascot", self.switch("mascot_animate"), "Turns itself off if your OS reduces motion")
        self.row(box, "Desktop notifications", self.switch("desktop_notify"))
        self.row(box, "Alert sound", self.switch("alert_sound"))
        self.row(box, "Quiet hours", self.switch("quiet_enabled"), "Banner only, no flash, sound, notification or mascot")

        def quiet(parent):
            fr = tk.Frame(parent, bg=th["surface"])
            self.entry("qfrom", 6)(fr).pack(side="left", ipady=px(2))
            tk.Label(fr, text="to", font=f["small"], fg=th["muted"], bg=th["surface"]).pack(side="left", padx=px(6))
            self.entry("qto", 6)(fr).pack(side="left", ipady=px(2))
            return fr
        self.row(box, "Quiet from", quiet, "24-hour times, e.g. 22:00 to 08:00")
        self.row(box, "Tell me when a window resets", self.switch("notify_reset"))
        self.row(box, "Run on alert", self.entry("hook", 18),
                 "Optional shell command (gets LIMITLINE_PCT / _LABEL / _EVENT)")

        box = self.section(right, "Live plan limits")
        live = app.live.get()
        status = {"ok": "Connected" + (f" · {live['plan']} plan" if live.get("plan") else ""),
                  "stale": "Connected (last update failed)", "off": "Off", "idle": "Checking…"}.get(
            live.get("status"), live.get("msg") or "Unavailable")
        self.row(box, "Show live limits", self.switch("live_limits"),
                 "Official source: Claude Code's status line (5-hour and weekly). " + status)

        def connect(parent):
            def go():
                app.connect_statusline()
            return app.button(parent, "Connect", go)
        self.row(box, "Connect Claude Code", connect,
                 "Adds a status-line command to Claude Code's settings. Backed up and reversible.")
        self.row(box, "Use saved login instead", self.switch("live_oauth"),
                 "Advanced, off by default. Reads Claude Code's login token and asks Anthropic directly; adds "
                 "per-model weekly limits. Anthropic's terms restrict third-party use of that token, so only "
                 "enable it if you accept that risk.")

        box = self.section(right, "Data")
        roots = log_roots(self.v.get("extra_paths") or [])
        found = "\n".join(shorten_path(r) for r in roots) or "No log folders found yet"
        self.row(box, "Log folders", lambda p: tk.Frame(p, bg=th["surface"]), found)

        def extra(parent):
            fr = tk.Frame(parent, bg=th["surface"])
            self.entry("extra", 16)(fr).pack(side="left", ipady=px(2))

            def browse():
                d = filedialog.askdirectory(parent=self.win, title="Choose a Claude log folder")
                if d:
                    self.vars["extra"].set(d)
            app.button(fr, "Browse…", browse).pack(side="left", padx=(px(6), 0))
            return fr
        self.row(box, "Extra folder", extra)

        for w in self.footbar.winfo_children():
            w.destroy()
        foot = self.footbar
        reset = tk.Label(foot, text="Reset to defaults", font=f["small"], fg=th["muted"], bg=th["bg"], cursor="hand2")
        reset.pack(side="left")
        reset.bind("<ButtonRelease-1>", lambda e: self.reset_defaults())
        app.button(foot, "Save", self.save, primary=True).pack(side="right")
        app.button(foot, "Cancel", self.cancel).pack(side="right", padx=(0, px(8)))
        self.win.after_idle(self.fit)

    def reset_defaults(self):
        keep = {k: self.v[k] for k in ("x", "y", "mini", "tab")}
        self.v = {k: (list(v) if isinstance(v, list) else v) for k, v in json.loads(json.dumps(DEFAULTS)).items()
                  if k != "alerted"}
        self.v.update(keep)
        self.vars["limit"].set("")
        self.vars["refresh"].set(str(DEFAULTS["refresh_sec"]))
        self.vars["levels"].set(", ".join(str(x) for x in DEFAULTS["alert_levels"]))
        self.vars["levels_week"].set(", ".join(str(x) for x in DEFAULTS["alert_levels_week"]))
        self.vars["step"].set("")
        self.vars["qfrom"].set(DEFAULTS["quiet_from"])
        self.vars["qto"].set(DEFAULTS["quiet_to"])
        self.vars["extra"].set("")
        self.vars["opacity"].set(int(DEFAULTS["opacity"] * 100))
        self.build()
        self.fit()

    def save(self):
        v, cfg = self.v, self.app.cfg
        v["opacity"] = min(1.0, max(0.4, self.vars["opacity"].get() / 100.0))
        try:
            v["refresh_sec"] = min(600, max(5, int(float(self.vars["refresh"].get()))))
        except ValueError:
            pass
        v["alert_levels"] = sorted({min(100, max(1, int(x))) for x in re.findall(r"\d+", self.vars["levels"].get())})
        v["alert_levels_week"] = sorted({min(100, max(1, int(x))) for x in re.findall(r"\d+", self.vars["levels_week"].get())})
        st = re.findall(r"\d+", self.vars["step"].get())
        v["alert_step"] = int(st[0]) if st and int(st[0]) >= 5 else 0
        for key, var, dflt in (("quiet_from", "qfrom", "22:00"), ("quiet_to", "qto", "08:00")):
            t = self.vars[var].get().strip()
            v[key] = t if re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", t) else dflt
        v["limit_value"] = parse_amount(self.vars["limit"].get())
        if v["limit_mode"] == "custom" and v["limit_value"] <= 0:
            v["limit_mode"] = "auto"
        v["on_alert_command"] = self.vars["hook"].get().strip()
        extra = self.vars["extra"].get().strip()
        v["extra_paths"] = [extra] if extra else []
        old = dict(cfg)
        cfg.update(v)
        if self.auto != autostart_enabled():
            set_autostart(self.auto)
        self.win.destroy()
        self.app.settings = None
        self.app.apply_settings(old)

    def cancel(self):
        try:
            self.app.root.attributes("-alpha", self.orig_alpha)
        except tk.TclError:
            pass
        self.win.destroy()
        self.app.settings = None


# =============================================================================
# main
# =============================================================================
class Welcome:
    """First-run window: three one-click steps."""

    def __init__(self, app):
        self.app, self.msg = app, ""
        th = app.th
        self.win = tk.Toplevel(app.root)
        self.win.title(f"Welcome · {APP_NAME}")
        self.win.configure(bg=th["bg"])
        self.win.resizable(False, False)
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.body = tk.Frame(self.win, bg=th["bg"])
        self.body.pack(padx=app.px(18), pady=app.px(16))
        self.auto = autostart_enabled()
        self.build()
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        x0, y0, x1, y1 = app.screen_bounds()
        rx, ry = app.root.winfo_x(), app.root.winfo_y()
        x = rx - w - app.px(12) if rx - w - app.px(12) > x0 else min(x1 - w - app.px(12), rx + app.px(40))
        self.win.geometry(f"+{int(x)}+{int(max(y0 + app.px(20), min(ry + app.px(30), y1 - h - app.px(60))))}")
        self.win.protocol("WM_DELETE_WINDOW", self.done)
        self.win.bind("<Escape>", lambda e: self.done())
        self.win.focus_force()

    def step(self, num, title, desc, make=None):
        app, th, f, px = self.app, self.app.th, self.app.f, self.app.px
        body, _ = app.card(self.body)
        left = tk.Frame(body, bg=th["surface"])
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=f"{num}  {title}", font=f["bodyb"], fg=th["ink"], bg=th["surface"], anchor="w").pack(anchor="w")
        tk.Label(left, text=desc, font=f["small"], fg=th["muted"], bg=th["surface"], anchor="w", justify="left",
                 wraplength=px(270)).pack(anchor="w", pady=(px(3), 0))
        if make:
            make(body).pack(side="right", padx=(px(10), 0))

    def build(self):
        app, th, f, px = self.app, self.app.th, self.app.f, self.app.px
        for w in self.body.winfo_children():
            w.destroy()
        tk.Label(self.body, text=f"Welcome to {APP_NAME}", font=f["h1"], fg=th["ink"], bg=th["bg"]).pack(anchor="w")
        tk.Label(self.body, text="Three quick things. Everything can be changed later in Settings (press S).",
                 font=f["small"], fg=th["muted"], bg=th["bg"]).pack(anchor="w", pady=(px(3), px(12)))
        roots = log_roots(app.cfg.get("extra_paths") or [])
        if roots:
            self.step("1", "Your Claude Code history", "Found " + ", ".join(shorten_path(r) for r in roots[:2]) + ".")
        else:
            self.step("1", "Your Claude Code history",
                      "No log folder yet. Use Claude Code once and it appears; you can also add a folder in Settings.")
        if statusline_connected():
            self.step("2", "Live plan limits", "Connected. Your real 5-hour and weekly limits show after your next "
                      "message in Claude Code.", lambda p: tk.Label(p, text="Connected", font=f["smallb"],
                                                                      fg=STATUS["good"], bg=th["surface"]))
        else:
            def connect(parent):
                def go():
                    ok, self.msg = app.connect_statusline()
                    self.build()
                return app.button(parent, "Connect", go, primary=True)
            self.step("2", "Live plan limits", "Uses Claude Code's official status line. No login access. "
                      "Your current status line keeps working, and you can undo it anytime.", connect)
        if self.msg:
            tk.Label(self.body, text=self.msg, font=f["tiny"], fg=th["ink2"], bg=th["bg"], wraplength=px(340),
                     justify="left").pack(anchor="w", pady=(0, px(6)))

        def switch(parent):
            return Switch(parent, app, self.auto, self.set_auto)
        self.step("3", "Start with your computer", "Opens Limitline when you sign in.", switch)
        foot = tk.Frame(self.body, bg=th["bg"])
        foot.pack(fill="x", pady=(px(4), 0))
        app.button(foot, "Done", self.done, primary=True).pack(side="right")

    def set_auto(self, on):
        self.auto = bool(on)
        set_autostart(self.auto)

    def done(self):
        self.app.cfg["welcomed"] = True
        self.app.save_soon()
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        self.app.live.wake.set()


# =============================================================================
# Self-test: run `python limitline.py --selftest` on any computer (esp. Windows)
# =============================================================================
def run_selftest(args):
    import tempfile
    import traceback
    lines, fails = [], []

    def out(msg):
        lines.append(msg)
        print(msg, flush=True)

    def check(name, fn):
        t0 = time.time()
        try:
            res = fn()
            ok, detail = (res if isinstance(res, tuple) else (True, res))
        except Exception as ex:  # noqa: BLE001
            ok, detail = False, "".join(traceback.format_exception_only(type(ex), ex)).strip()
            lines.append(traceback.format_exc())
        out(f"{'PASS' if ok else 'FAIL'}  {name}  ({(time.time() - t0) * 1000:.0f} ms)" + (f"  {detail}" if detail else ""))
        if not ok:
            fails.append(name)

    global CONFIG_PATH
    real_cfg = CONFIG_PATH
    tmp = tempfile.mkdtemp(prefix="limitline-selftest-")
    CONFIG_PATH = os.path.join(tmp, ".limitline.json")          # never touch the real settings
    saved_env = os.environ.get("CLAUDE_CONFIG_DIR")
    out(f"Limitline {VERSION} self-test")
    out(f"Python {sys.version.split()[0]} on {sys.platform} ({os.name}), exe: {sys.executable}")

    check("tkinter available", lambda: (tk is not None, f"Tk {tk.TkVersion}" if tk else "missing"))
    check("config save/load round-trip", lambda: (
        (lambda c0: (c0.update(opacity=0.8, alert_levels=[50, 95]), save_config(c0), load_config())[2])(load_config())
        .get("alert_levels") == [50, 95]))

    def logs():
        roots = log_roots([])
        st = LogStore()
        t0 = time.time()
        st.scan(roots, 0)
        es = st.entries(0)
        return True, f"{len(roots)} log folder(s), {len(es):,} messages in {time.time() - t0:.1f}s; unpriced: {list(st.unpriced) or 'none'}"
    check("read your Claude Code logs", logs)

    def statusline():
        cdir = os.path.join(tmp, "my acct")                      # a space in the path exercises shell quoting
        os.makedirs(cdir)
        os.environ["CLAUDE_CONFIG_DIR"] = cdir
        sp = os.path.join(cdir, "settings.json")
        with open(sp, "w", encoding="utf-8") as fh:
            json.dump({"statusLine": {"type": "command", "command": "echo OLD"}}, fh)
        global CONFIG_PATH
        CONFIG_PATH = os.path.join(cdir, ".limitline.json")      # the live file sits next to the settings file
        ok, msg = install_statusline(cdir)
        cmd = json.load(open(sp, encoding="utf-8"))["statusLine"]["command"]
        payload = json.dumps({"rate_limits": {"five_hour": {"used_percentage": 12.5, "resets_at": time.time() + 3000}}})
        r = subprocess.run(cmd, shell=True, input=payload, capture_output=True, text=True, timeout=30)
        chained = "OLD" in r.stdout
        read = read_bridge()
        ok2, _ = uninstall_statusline()
        restored = json.load(open(sp, encoding="utf-8"))["statusLine"]["command"] == "echo OLD"
        CONFIG_PATH = os.path.join(tmp, ".limitline.json")
        good = ok and r.returncode == 0 and chained and bool(read and read[0]) and ok2 and restored
        return good, f"command ran via the shell: exit {r.returncode}, chained={chained}, saved={bool(read)}, restored={restored}"
    check("status-line connect / run / undo (shell quoting)", statusline)
    os.environ.pop("CLAUDE_CONFIG_DIR", None) if saved_env is None else os.environ.__setitem__("CLAUDE_CONFIG_DIR", saved_env)

    def autostart():
        before = autostart_enabled()
        set_autostart(True)
        on = autostart_enabled()
        set_autostart(False)
        off = not autostart_enabled()
        if before:
            set_autostart(True)
        return on and off, f"entry: {autostart_path()}"
    check("launch-at-login entry (written then removed)", autostart)

    def lock():
        s1 = socket.socket()
        try:
            s1.bind(("127.0.0.1", INSTANCE_PORT))
            return True, f"port {INSTANCE_PORT} free"
        except OSError:
            return True, f"port {INSTANCE_PORT} in use (another copy is running; that is fine)"
        finally:
            s1.close()
    check("single-instance port", lock)

    def notify():
        notify_desktop("Limitline self-test", "If you can see this notification, alerts work.")
        return True, "sent - did a notification appear?"
    check("desktop notification", notify)

    if tk is not None:
        try:
            root = tk.Tk()
        except Exception as ex:  # noqa: BLE001
            out(f"FAIL  open a window  {ex}")
            fails.append("open a window")
            root = None
        if root is not None:
            args.demo, args.multi, args.no_live = "live", True, False
            cfg = load_config(reset=True)
            cfg["x"] = cfg["y"] = None
            holder = {}
            t0 = time.time()
            try:
                holder["app"] = App(root, cfg, args)
                root.update()
                out(f"PASS  build the window  ({(time.time() - t0) * 1000:.0f} ms)")
            except Exception:  # noqa: BLE001
                out("FAIL  build the window\n" + traceback.format_exc())
                fails.append("build the window")
            app = holder.get("app")
            if app:
                fams = app.f
                out(f"info  display scale x{app.S:.2f} (dpi {root.winfo_fpixels('1i'):.0f}), screen {root.winfo_screenwidth()}x{root.winfo_screenheight()}, "
                    f"UI font {fams['body'].actual('family')!r}, numerals {fams['hero'].actual('family')!r}")
                for key, _label in app.TABS:
                    def tab(key=key):
                        app.set_tab(key)
                        root.update()
                        root.update_idletasks()
                        w, h = root.winfo_width(), root.winfo_height()
                        bx0, by0, bx1, by1 = app.screen_bounds()
                        fits = h <= (by1 - by0) and w <= (bx1 - bx0)
                        return fits, f"window {w}x{h}" + ("" if fits else "  (larger than the screen!)")
                    check(f"render the {key} tab", tab)
                for theme in ("light", "dark"):
                    def th(theme=theme):
                        app.cfg["theme"] = theme
                        app.th = make_theme(theme, app.cfg["accent"])
                        app.build()
                        root.update()
                        return True, ""
                    check(f"{theme} theme", th)

                def mini():
                    app.toggle_mini()
                    root.update()
                    w = root.winfo_width()
                    app.toggle_mini()
                    root.update()
                    return w < root.winfo_width(), f"mini width {w}px"
                check("mini pill and back", mini)

                def settings():
                    app.open_settings()
                    root.update()
                    ok = app.settings is not None and app.settings.win.winfo_exists()
                    sw, sh = app.settings.win.winfo_width(), app.settings.win.winfo_height()
                    app.settings.win.destroy()
                    return ok, f"settings window {sw}x{sh}"
                check("settings window", settings)

                def small_screen():
                    real = app.screen_bounds
                    app.screen_bounds = lambda: (0, 0, 1366, 728)        # a common laptop after the taskbar
                    try:
                        app.open_settings()
                        root.update()
                        root.update_idletasks()
                        h = app.settings.win.winfo_reqheight()
                        scrolls = getattr(app.settings, "scrolls", False)
                        app.settings.win.destroy()
                        app.settings = None
                    finally:
                        app.screen_bounds = real
                    return h <= 728, f"settings is {h}px tall on a 728px screen" + (" (scrolls)" if scrolls else "")
                check("settings fits a 1366x768 laptop", small_screen)

                def mascot_check():
                    ev = {"kind": "threshold", "scope": "session", "level": 90, "pct": 92, "label": "x",
                          "text": "x", "title": "x"}
                    saved = app.cfg.get("mascot")
                    app.cfg["mascot"] = "full"
                    try:
                        app.mascot.event(ev)
                        end = time.time() + 15
                        while time.time() < end and app.mascot.win is None:
                            root.update()
                            time.sleep(0.05)
                        ok = app.mascot.win is not None and len(app.mascot.frames) >= 1
                        app.mascot.hide()
                    finally:
                        app.cfg["mascot"] = saved
                    return ok, "mascot card appeared" if ok else "mascot card did not appear"
                check("alert mascot shows", mascot_check)

                def welcome():
                    app.open_welcome()
                    root.update()
                    ok = app.welcome.win.winfo_exists()
                    app.welcome.win.destroy()
                    return ok, ""
                check("first-run welcome window", welcome)

                def tweaks():
                    if IS_WIN:
                        app.win_tweaks()
                        root.update()
                    return True, "Windows rounded-corner / dark title-bar call completed" if IS_WIN else "n/a on this OS"
                check("window tweaks", tweaks)
            try:
                root.destroy()
            except Exception:  # noqa: BLE001
                pass

    CONFIG_PATH = real_cfg
    out("")
    out("RESULT: " + ("ALL CHECKS PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails)))
    out("Please also look at the window with demo data:  python limitline.py --demo   (check icons are smooth, text isn't cut off)")
    rp = os.path.join(os.path.expanduser("~"), "limitline-selftest.txt")
    try:
        with open(rp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"Report saved to {rp}")
    except OSError:
        pass
    return 0 if not fails else 1


def main():
    ap = argparse.ArgumentParser(description="Floating monitor for your Claude Code usage.")
    ap.add_argument("--demo", nargs="?", const="live", choices=["live", "local"],
                    help="preview with sample data (local = without live plan limits)")
    ap.add_argument("--mini", action="store_true", help="start as the small pill")
    ap.add_argument("--theme", choices=["dark", "light"])
    ap.add_argument("--refresh", type=int, metavar="SEC")
    ap.add_argument("--path", action="append", metavar="DIR", help="extra log folder (repeatable)")
    ap.add_argument("--no-live", action="store_true", help="don't fetch live plan limits")
    ap.add_argument("--reset", action="store_true", help="forget saved settings")
    ap.add_argument("--multi", action="store_true", help="allow more than one copy")
    ap.add_argument("--config-dir", metavar="DIR",
                    help="watch another Claude account (its Claude config folder); implies --multi")
    ap.add_argument("--setup", action="store_true", help="show the first-run welcome window")
    ap.add_argument("--autostart", choices=["on", "off"], help="turn launch-at-login on or off, then exit")
    ap.add_argument("--selftest", action="store_true", help="check this computer end to end and save a report")
    ap.add_argument("--statusline", action="store_true",
                    help="run as Claude Code's status-line command (reads JSON on stdin)")
    ap.add_argument("--then", metavar="CMD", help="with --statusline: another status-line command to keep running")
    ap.add_argument("--install-statusline", action="store_true",
                    help="connect live plan limits via Claude Code's official status line")
    ap.add_argument("--uninstall-statusline", action="store_true", help="undo --install-statusline")
    ap.add_argument("--tab", choices=["overview", "history", "projects", "sessions"], help=argparse.SUPPRESS)
    ap.add_argument("--open-settings", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    global CONFIG_PATH, APP_NAME
    if args.config_dir:
        d = os.path.abspath(os.path.expanduser(args.config_dir))
        os.environ["CLAUDE_CONFIG_DIR"] = d
        CONFIG_PATH = os.path.join(d, ".limitline.json")
        APP_NAME = f"{APP_NAME} [{os.path.basename(d.rstrip(os.sep)) or d}]"
        args.multi = True
    if args.statusline:
        run_statusline(args.then)
        return
    if args.autostart:
        ok = set_autostart(args.autostart == "on")
        print(f"Launch at login {'enabled' if args.autostart == 'on' else 'disabled'}." if ok else "Couldn't change the startup entry.")
        sys.exit(0 if ok else 1)
    if args.selftest:
        sys.exit(run_selftest(args))
    if args.install_statusline or args.uninstall_statusline:
        ok, msg = (install_statusline(args.config_dir) if args.install_statusline else uninstall_statusline())
        print(msg)
        sys.exit(0 if ok else 1)
    if tk is None:
        print("tkinter isn't available in this Python. On Linux install python3-tk; on Windows/macOS use the "
              "python.org installer.", file=sys.stderr)
        sys.exit(1)

    lock = None
    if not (args.multi or args.demo):
        lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            lock.bind(("127.0.0.1", INSTANCE_PORT))
        except OSError:
            print(f"{APP_NAME} is already running (use --multi to start another).", file=sys.stderr)
            sys.exit(0)

    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:  # noqa: BLE001
                pass

    cfg = load_config(reset=args.reset)
    if args.theme:
        cfg["theme"] = args.theme
    if args.refresh:
        cfg["refresh_sec"] = min(600, max(5, args.refresh))
    if args.mini:
        cfg["mini"] = True
    if args.tab:
        cfg["tab"], cfg["mini"] = args.tab, False
    if args.demo:
        cfg["x"] = cfg["y"] = None

    root = tk.Tk()
    App(root, cfg, args)
    root.mainloop()
    if lock:
        lock.close()


if __name__ == "__main__":
    main()
