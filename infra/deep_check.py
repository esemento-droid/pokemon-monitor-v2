#!/usr/bin/env python3
"""Deep check — dead shops, scan frequency, watchdog analysis."""
import subprocess
import re
from collections import defaultdict
from datetime import datetime, timedelta

# Get last 3 hours of logs for better picture
result = subprocess.run(
    ["journalctl", "-u", "pokemon-monitor-v2", "--since", "3 hours ago", "--no-pager", "-o", "cat"],
    capture_output=True, text=True, timeout=60
)
lines = result.stdout.splitlines()

# Track per-shop: successful scans vs timeouts (3h window)
shops_success = defaultdict(int)
shops_timeout_count = defaultdict(int)
shops_last_products = {}
shops_last_time = {}
shops_errors = defaultdict(list)

for line in lines:
    # Successful scan
    m = re.search(r'\[(FAST|SLOW|NODRIVER|ENGINE)\].*\[(\w[\w-]*)\]\s+(\d+)\s+produkt', line)
    if m:
        shop = m.group(2)
        count = int(m.group(3))
        shops_success[shop] += 1
        shops_last_products[shop] = count
        tm = re.search(r'w\s+([\d.]+)s', line)
        if tm:
            shops_last_time[shop] = float(tm.group(1))
        continue

    m = re.search(r'\[(\w[\w-]*)\]\s+(\d+)\s+pre-order', line)
    if m:
        shops_success[m.group(1)] += 1
        shops_last_products[m.group(1)] = int(m.group(2))
        continue

    # Also catch [SHOPNAME] N produktow format
    m = re.search(r'^\[(\w[\w-]*)\]\s+(\d+)\s+produkt', line)
    if m:
        shop = m.group(1).lower()
        shops_success[shop] += 1
        shops_last_products[shop] = int(m.group(2))
        continue

    # Timeout
    m = re.search(r'\[(FAST|SLOW|NODRIVER)\].*\[WARNING\].*\[(\w[\w-]*)\]\s+Timeout', line)
    if m:
        shops_timeout_count[m.group(2)] += 1
        continue
    m = re.search(r'\[(NODRIVER)\].*\[WARNING\].*\[(\w[\w-]*)\]\s+TIMEOUT', line)
    if m:
        shops_timeout_count[m.group(2)] += 1
        continue

    # Errors (not timeout)
    m = re.search(r'\[(FAST|SLOW|NODRIVER|ENGINE)\].*\[(ERROR)\].*\[(\w[\w-]*)\](.+)', line)
    if m:
        shops_errors[m.group(3)].append(m.group(4).strip()[:60])

# All known shops
all_shops = set(shops_success.keys()) | set(shops_timeout_count.keys())

print("=" * 70)
print(f"  DEEP CHECK — last 3 hours ({len(lines)} log lines)")
print(f"  Total unique shops seen: {len(all_shops)}")
print("=" * 70)

# === DEAD SHOPS (only timeouts, zero success in 3h) ===
dead = []
for shop in all_shops:
    if shops_success.get(shop, 0) == 0 and shops_timeout_count.get(shop, 0) > 0:
        dead.append((shop, shops_timeout_count[shop]))
dead.sort(key=lambda x: x[1], reverse=True)

print()
print("-" * 70)
print(f"  💀 DEAD SHOPS (0 successful scans in 3h, only timeouts): {len(dead)}")
print("-" * 70)
for shop, to_count in dead:
    errs = shops_errors.get(shop, [])
    err_info = f" | last error: {errs[-1][:50]}" if errs else ""
    print(f"    {shop:30s} {to_count:3d}x timeout{err_info}")

# === STRUGGLING (success rate < 30%) ===
struggling = []
for shop in all_shops:
    s = shops_success.get(shop, 0)
    t = shops_timeout_count.get(shop, 0)
    total = s + t
    if total > 3 and s > 0 and s / total < 0.30:
        struggling.append((shop, s, t, s/total*100))
struggling.sort(key=lambda x: x[3])

print()
print("-" * 70)
print(f"  ⚠️ STRUGGLING SHOPS (success rate < 30%): {len(struggling)}")
print("-" * 70)
for shop, s, t, rate in struggling:
    products = shops_last_products.get(shop, "?")
    print(f"    {shop:30s} {s:2d} OK / {t:2d} timeout = {rate:4.0f}%  (last: {products} products)")

# === HEALTHY (success rate > 70%) ===
healthy = []
for shop in all_shops:
    s = shops_success.get(shop, 0)
    t = shops_timeout_count.get(shop, 0)
    total = s + t
    if total > 0 and s > 0 and s / total >= 0.70:
        healthy.append((shop, s, t, shops_last_products.get(shop, 0)))
healthy.sort(key=lambda x: x[3], reverse=True)

print()
print("-" * 70)
print(f"  ✅ HEALTHY SHOPS (success rate >= 70%): {len(healthy)}")
print("-" * 70)
for shop, s, t, products in healthy[:30]:
    rate = s / (s + t) * 100
    time_s = f"{shops_last_time[shop]:.0f}s" if shop in shops_last_time else ""
    print(f"    {shop:30s} {s:3d} OK / {t:2d} fail = {rate:3.0f}%  {products:4d} products  {time_s}")
print(f"    ... and {len(healthy)-30} more") if len(healthy) > 30 else None

# === SCAN FREQUENCY ===
print()
print("-" * 70)
print("  📊 SCAN FREQUENCY (successful scans in 3h):")
print("-" * 70)
freq_groups = {"10+ scans": 0, "5-9 scans": 0, "2-4 scans": 0, "1 scan": 0, "0 (dead)": len(dead)}
for shop in all_shops:
    s = shops_success.get(shop, 0)
    if s >= 10: freq_groups["10+ scans"] += 1
    elif s >= 5: freq_groups["5-9 scans"] += 1
    elif s >= 2: freq_groups["2-4 scans"] += 1
    elif s == 1: freq_groups["1 scan"] += 1
for group, count in freq_groups.items():
    bar = "█" * count
    print(f"    {group:12s}: {count:3d} shops  {bar}")

# === WATCHDOG ANALYSIS ===
print()
print("=" * 70)
print("  🐕 PHONE WATCHDOG ANALYSIS (last 3h)")
print("=" * 70)
wdog = subprocess.run(
    ["sshpass", "-p", "123", "ssh", "-o", "StrictHostKeyChecking=no",
     "-o", "ConnectTimeout=10", "-p", "8022", "100.127.72.24",
     "tail -100 ~/logs/watchdog.log 2>/dev/null; echo '---CRONTAB---'; crontab -l 2>/dev/null"],
    capture_output=True, text=True, timeout=20
)
if wdog.returncode == 0:
    wdog_lines = wdog.stdout.splitlines()
    # Count events
    vps_unreachable = sum(1 for l in wdog_lines if "VPS UNREACHABLE" in l)
    autossh_dead = sum(1 for l in wdog_lines if "AUTOSSH DEAD" in l)
    autossh_force = sum(1 for l in wdog_lines if "FORCE-RESTARTED" in l)
    tinyproxy_dead = sum(1 for l in wdog_lines if "TINYPROXY DEAD" in l)
    autossh_fail = sum(1 for l in wdog_lines if "FAILED TO START" in l)
    autossh_restored = sum(1 for l in wdog_lines if "AUTOSSH RESTORED" in l)
    tinyproxy_restored = sum(1 for l in wdog_lines if "TINYPROXY RESTORED" in l)

    print(f"  Last 100 log entries:")
    print(f"    VPS UNREACHABLE:      {vps_unreachable}")
    print(f"    AUTOSSH FORCE-RESTART: {autossh_force}")
    print(f"    AUTOSSH DEAD:          {autossh_dead}")
    print(f"    AUTOSSH RESTORED:      {autossh_restored}")
    print(f"    AUTOSSH FAILED:        {autossh_fail}")
    print(f"    TINYPROXY DEAD:        {tinyproxy_dead}")
    print(f"    TINYPROXY RESTORED:    {tinyproxy_restored}")
    print()

    # Show watchdog.sh content
    print("  Current watchdog.sh on phone:")
    in_crontab = False
    watchdog_content = []
    for l in wdog_lines:
        if "---CRONTAB---" in l:
            in_crontab = True
            continue
        if in_crontab:
            print(f"    CRON: {l}")

    # Show last 10 watchdog entries with timestamps
    print()
    print("  Last 10 watchdog events:")
    events = [l for l in wdog_lines if "---CRONTAB---" not in l and l.strip()]
    for l in events[-10:]:
        print(f"    {l}")
else:
    print(f"  ERROR: Cannot SSH to phone: {wdog.stderr[:100]}")

# === VPS WATCHDOG ===
print()
print("-" * 70)
print("  🖥️ VPS PROXY WATCHDOG (proxy_watchdog.sh log):")
print("-" * 70)
try:
    with open("/opt/pokemon-monitor-v2/proxy_watchdog.log") as f:
        vps_wdog = f.readlines()[-15:]
    for l in vps_wdog:
        print(f"    {l.rstrip()}")
    if not vps_wdog:
        print("    (empty — means proxy never died, watchdog exits silently)")
except FileNotFoundError:
    print("    (no log file — proxy_watchdog.sh never needed to repair)")

print()
print("=" * 70)
print("  DEEP CHECK COMPLETE")
print("=" * 70)
