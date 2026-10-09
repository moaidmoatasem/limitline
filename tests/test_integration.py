"""Integration tests for Limitline - end-to-end scenarios.

Run: python tests/test_integration.py
"""
import os
import sys
import json
import time
import tempfile
import subprocess
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

# =========================================================================
# Scenario 1: Full app startup -> log scan -> snapshot -> render (no display)
# =========================================================================
def test_full_startup_pipeline():
    print("\n=== Scenario 1: Full startup pipeline ===")
    tmp = tempfile.mkdtemp()
    proj = os.path.join(tmp, "projects", "-Users-moayed-code-web-app")
    os.makedirs(proj)
    f1 = os.path.join(proj, "s1.jsonl")
    with open(f1, "w") as fh:
        fh.write(line(now - 590, "msg_A", "req_A", "claude-sonnet-5-5", 10, 120, 1000, 20000, w1=1000))
        fh.write(line(now - 500, "msg_B", "req_B", "claude-opus-5-5", 5, 1000, 4000, 50000))
    
    store = c.LogStore()
    changed, nfiles = store.scan([os.path.join(tmp, "projects")], now - 40 * 86400)
    check(changed == 1 and nfiles == 1, "scanned 1 file")
    es = store.entries(now - 40 * 86400)
    check(len(es) == 2, "2 entries after scan")
    
    cfg = c.load_config(reset=True)
    snap = c.build_snapshot(es, time.time(), cfg, {"status": "off"}, {"roots": [tmp], "files": 1, "entries": 2, "demo": False})
    check(snap["has_data"], "snapshot has data")
    check(snap["window"] is not None, "has active window")
    check(snap["kpi"]["30d"]["agg"][4] > 0, "cost computed")
    
    # Verify render functions don't crash (headless - no display)
    # We can't test actual rendering without display, but we can verify
    # the data structures are correct for rendering
    check("daily" in snap and "hourly" in snap and "heat" in snap, "snapshot has render data")

# =========================================================================
# Scenario 2: LiveLimits.fetch -> parse_live -> build_snapshot -> render_limits_card
# =========================================================================
def test_live_limits_pipeline():
    print("\n=== Scenario 2: Live limits pipeline ===")
    # Mock live data with proper structure
    live_data = {"status": "ok", "source": "statusline", "fetched": time.time(),
                 "items": [
                     {"key": "five_hour", "label": "5-hour", "pct": 35.0, "resets_at": "2026-02-06T22:00:00+00:00"},
                     {"key": "seven_day", "label": "Weekly", "pct": 14.0, "resets_at": "2026-02-12T20:00:00.123456+00:00"},
                     {"key": "seven_day_sonnet", "label": "Weekly · Sonnet", "pct": 39.0, "resets_at": "2026-02-09T14:00:00+00:00"}],
                 "extra": {"is_enabled": True, "monthly_limit": 100000, "used_credits": 2500.0}}
    
    items, extra = c.parse_live({"five_hour": {"utilization": 35.0, "resets_at": "2026-02-06T22:00:00+00:00"},
                                 "seven_day": {"utilization": 14.0, "resets_at": "2026-02-12T20:00:00.123456+00:00"},
                                 "seven_day_sonnet": {"utilization": 39.0, "resets_at": "2026-02-09T14:00:00+00:00"},
                                 "extra_usage": {"is_enabled": True, "monthly_limit": 100000, "used_credits": 2500.0}})
    check(len(items) == 3, "3 live items parsed")
    check(extra is not None and abs(extra["pct"] - 2.5) < 1e-9, "extra usage parsed")
    
    # Build snapshot with live data
    tmp = tempfile.mkdtemp()
    proj = os.path.join(tmp, "projects", "-Users-moayed-code-web-app")
    os.makedirs(proj)
    f1 = os.path.join(proj, "s1.jsonl")
    with open(f1, "w") as fh:
        fh.write(line(now - 590, "msg_A", "req_A", "claude-sonnet-5-5", 10, 120, 1000, 20000, w1=1000))
    
    store = c.LogStore()
    store.scan([os.path.join(tmp, "projects")], now - 40 * 86400)
    es = store.entries(now - 40 * 86400)
    
    cfg = c.load_config(reset=True)
    live_obj = {"status": "ok", "source": "statusline", "fetched": time.time(),
                "items": [
                    {"key": "five_hour", "label": "5-hour", "pct": 35.0, "resets": time.time() + 3600},
                    {"key": "seven_day", "label": "Weekly", "pct": 14.0, "resets": time.time() + 86400},
                    {"key": "seven_day_sonnet", "label": "Weekly · Sonnet", "pct": 39.0, "resets": time.time() + 86400}],
                "extra": {"pct": 2.5, "used": 2500.0, "limit": 100000.0}}
    snap = c.build_snapshot(es, time.time(), cfg, live_obj, {"roots": [tmp], "files": 1, "entries": len(es), "demo": False})
    
    check(snap["live"]["status"] == "ok", "live status ok")
    check(snap["window"]["src"] == "live", "live window drives gauge")
    check(snap["gauge"]["pct"] == 35.0, "live percentage drives gauge")
    check("extra" in snap["live"], "extra usage in snapshot")

# =========================================================================
# Scenario 3: Status-line hook end-to-end
# =========================================================================
def test_statusline_bridge():
    print("\n=== Scenario 3: Status-line bridge ===")
    td = tempfile.mkdtemp()
    cfgdir = os.path.join(td, "acct")
    os.makedirs(cfgdir)
    env = dict(os.environ, CLAUDE_CONFIG_DIR=cfgdir, HOME=td)
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "limitline.py")
    
    payload = {"session_id": "x", "transcript_path": "/secret/path", "cwd": "/secret",
               "rate_limits": {"five_hour": {"used_percentage": 23.5, "resets_at": time.time() + 3600},
                              "seven_day": {"used_percentage": 41.2, "resets_at": time.time() + 86400}}}
    
    r = subprocess.run([sys.executable, script, "--statusline", "--config-dir", cfgdir],
                       input=json.dumps(payload).encode("utf-8"), capture_output=True, env=env, timeout=20)
    
    check(r.returncode == 0, "statusline exits cleanly")
    check(r.stdout.decode("utf-8").strip() == "5h 23.5% · 7d 41.2%", f"statusline output correct: {r.stdout}")
    
    # Verify bridge file
    live_file = c.live_file_path()
    # The live file is written to CLAUDE_CONFIG_DIR/.limitline-live.json
    live_path = os.path.join(cfgdir, ".limitline-live.json")
    check(os.path.exists(live_path), "live file created")
    with open(live_path) as fh:
        live_data = json.load(fh)
    check("rate_limits" in live_data, "bridge file has rate_limits")
    check("five_hour" in live_data["rate_limits"], "five_hour in bridge")
    check(abs(live_data["rate_limits"]["five_hour"]["used_percentage"] - 23.5) < 1e-9, "5h percentage correct")

# =========================================================================
# Scenario 4: Config change at runtime -> watch_config -> reload -> re-render
# =========================================================================
def test_config_reload():
    print("\n=== Scenario 4: Config reload ===")
    tmp = tempfile.mkdtemp()
    cfgdir = os.path.join(tmp, "config")
    os.makedirs(cfgdir)
    cfg_file = os.path.join(cfgdir, ".limitline.json")
    
    # Start with one config - need to set CONFIG_PATH global
    old_cfg = c.CONFIG_PATH
    try:
        c.CONFIG_PATH = cfg_file
        initial = {"theme": "dark", "history_days": 30, "hist_range": 14}
        json.dump(initial, open(cfg_file, "w"))
        
        cfg = c.load_config()
        check(cfg["theme"] == "dark", "initial theme loaded")
        check(cfg["history_days"] == 30, "initial history_days loaded")
        check(cfg["hist_range"] == 30, "initial hist_range loaded")
        
        # Modify config file
        updated = {"theme": "light", "history_days": 180, "hist_range": 90}
        json.dump(updated, open(cfg_file, "w"))
        
        # Simulate watch_config detecting change and reloading
        new_cfg = c.load_config()
        check(new_cfg["theme"] == "light", "theme updated")
        check(new_cfg["history_days"] == 180, "history_days updated")
        check(new_cfg["hist_range"] == 90, "hist_range updated")
        
        # Verify config file was not corrupted
        check(os.path.exists(cfg_file), "config file exists")
        with open(cfg_file) as fh:
            final = json.load(fh)
        check(final == updated, "config file correctly written")
    finally:
        c.CONFIG_PATH = old_cfg

# =========================================================================
# Scenario 5: Status-line chaining with foreign status line
# =========================================================================
def test_statusline_chaining():
    print("\n=== Scenario 5: Status-line chaining ===")
    fdir = tempfile.mkdtemp()
    old_cfg = c.CONFIG_PATH
    c.CONFIG_PATH = os.path.join(fdir, ".limitline.json")
    try:
        os.environ["CLAUDE_CONFIG_DIR"] = fdir
        osp = os.path.join(fdir, "settings.json")
        
        # Start with a foreign status line
        json.dump({"statusLine": {"type": "command", "command": "mytool --statusline"}}, open(osp, "w"))
        check(c.statusline_connected() is False, "foreign status line not ours")
        
        # Install ours - should wrap the foreign one
        ok, msg = c.install_statusline(fdir)
        check(ok, "install succeeded")
        
        wrapped = json.load(open(osp))["statusLine"]["command"]
        check("mytool --statusline" in wrapped, "foreign status line kept")
        check(" --then " in wrapped, "chain separator present")
        check("limitline.py" in wrapped, "our status line added")
        
        check(c.statusline_connected() is True, "ours recognised after connect")
        
        # Uninstall - should restore foreign
        ok, msg = c.uninstall_statusline()
        check(ok, "uninstall succeeded")
        check(json.load(open(osp))["statusLine"]["command"] == "mytool --statusline",
              "uninstall restores foreign status line exactly")
    finally:
        c.CONFIG_PATH = old_cfg

# Run all scenarios
if __name__ == "__main__":
    test_full_startup_pipeline()
    test_live_limits_pipeline()
    test_statusline_bridge()
    test_config_reload()
    test_statusline_chaining()
    
    print("\n" + "=" * 50)
    print("FAILURES:", fails if fails else "none")
    print("=" * 50)
    
    if fails:
        sys.exit(1)