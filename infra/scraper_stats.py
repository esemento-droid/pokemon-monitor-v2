#!/usr/bin/env python3
"""Full scraper stats — checks all shops from last hour of logs."""
import subprocess
import re
from collections import defaultdict
from datetime import datetime, timedelta

# Get last 60 min of journalctl logs
result = subprocess.run(
    ["journalctl", "-u", "pokemon-monitor-v2", "--since", "60 min ago", "--no-pager", "-o", "cat"],
    capture_output=True, text=True, timeout=30
)
lines = result.stdout.splitlines()

# Parse results
shops_ok = {}       # shop -> last product count
shops_err = defaultdict(list)  # shop -> [error messages]
shops_timeout = defaultdict(int)  # shop -> timeout count
shops_time = {}     # shop -> last scan time (seconds)
total_scans = 0
total_errors = 0
total_timeouts = 0

for line in lines:
    # [FAST] [INFO] [shopname] N produktow w Xs
    m = re.search(r'\[(FAST|SLOW|NODRIVER|ENGINE)\].*\[(\w[\w-]*)\]\s+(\d+)\s+produkt', line)
    if m:
        shop = m.group(2)
        count = int(m.group(3))
        shops_ok[shop] = count
        total_scans += 1
        # Extract time
        tm = re.search(r'w\s+([\d.]+)s', line)
        if tm:
            shops_time[shop] = float(tm.group(1))
        continue

    # pre-order products (engine)
    m = re.search(r'\[(\w[\w-]*)\]\s+(\d+)\s+pre-order', line)
    if m:
        shop = m.group(1)
        count = int(m.group(2))
        shops_ok[shop] = count
        total_scans += 1
        continue

    # Timeout
    m = re.search(r'\[(FAST|SLOW|NODRIVER)\].*\[WARNING\].*\[(\w[\w-]*)\]\s+Timeout', line)
    if m:
        shop = m.group(2)
        shops_timeout[shop] += 1
        total_timeouts += 1
        continue

    # NODRIVER TIMEOUT subprocess
    m = re.search(r'\[(NODRIVER)\].*\[WARNING\].*\[(\w[\w-]*)\]\s+TIMEOUT', line)
    if m:
        shop = m.group(2)
        shops_timeout[shop] += 1
        total_timeouts += 1
        continue

    # Errors
    m = re.search(r'\[(FAST|SLOW|NODRIVER|ENGINE)\].*\[(ERROR|WARNING)\].*\[(\w[\w-]*)\](.+)', line)
    if m and 'Timeout' not in m.group(4):
        shop = m.group(3)
        msg = m.group(4).strip()[:80]
        shops_err[shop].append(msg)
        total_errors += 1
        continue

    # [SHOPNAME] 0 produktow (no category prefix — some shops log differently)
    m = re.search(r'^\[(\w[\w-]*)\]\s+(\d+)\s+produkt', line)
    if m:
        shop = m.group(1).lower()
        count = int(m.group(2))
        shops_ok[shop] = count
        total_scans += 1

print("=" * 70)
print(f"  SCRAPER STATS — last 60 minutes ({len(lines)} log lines)")
print("=" * 70)
print()
print(f"  Total successful scans: {total_scans}")
print(f"  Total timeouts:         {total_timeouts}")
print(f"  Total errors:           {total_errors}")
print(f"  Unique shops OK:        {len(shops_ok)}")
print(f"  Unique shops timeout:   {len(shops_timeout)}")
print(f"  Unique shops error:     {len(shops_err)}")
print()

# OK shops
print("-" * 70)
print("  ✅ WORKING SHOPS (found products):")
print("-" * 70)
sorted_ok = sorted(shops_ok.items(), key=lambda x: x[1], reverse=True)
for shop, count in sorted_ok:
    time_str = f"{shops_time[shop]:.0f}s" if shop in shops_time else ""
    err_flag = " ⚠️" if shop in shops_err else ""
    print(f"    {shop:30s} {count:4d} products  {time_str:>6s}{err_flag}")

print()
print("-" * 70)
print("  ❌ TIMEOUT SHOPS (no response):")
print("-" * 70)
sorted_to = sorted(shops_timeout.items(), key=lambda x: x[1], reverse=True)
for shop, count in sorted_to:
    also_ok = " (but also OK)" if shop in shops_ok else ""
    print(f"    {shop:30s} {count:2d}x timeout{also_ok}")

print()
print("-" * 70)
print("  ⚠️ ERROR SHOPS (errors other than timeout):")
print("-" * 70)
sorted_err = sorted(shops_err.items(), key=lambda x: len(x[1]), reverse=True)
for shop, msgs in sorted_err[:20]:
    also_ok = " ✅" if shop in shops_ok else " ❌"
    print(f"    {shop:30s} {len(msgs):2d} errors{also_ok}")
    for msg in msgs[-2:]:  # last 2 errors
        print(f"      └ {msg[:70]}")

print()
print("-" * 70)
print("  📊 SLOWEST SHOPS (scan time):")
print("-" * 70)
sorted_time = sorted(shops_time.items(), key=lambda x: x[1], reverse=True)[:15]
for shop, t in sorted_time:
    bar = "█" * min(int(t / 30), 20)
    print(f"    {shop:30s} {t:6.0f}s  {bar}")

print()
print("=" * 70)
