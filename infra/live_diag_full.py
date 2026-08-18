#!/usr/bin/env python3
"""
Full live diagnostics — last 30 minutes.
Covers: processes, RAM/CPU, logs, scan times, errors, proxy, Chrome, cron, disk.
Output goes to stdout (pipe to paste.rs).
"""
import subprocess
import re
import os
from datetime import datetime

def run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

print(f"=== LIVE DIAGNOSTICS — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")

# 1. UPTIME + LOAD
section("1. SYSTEM — uptime, load, RAM, swap")
print(run("uptime"))
print()
print(run("free -m"))
print()
print(run("cat /proc/loadavg"))

# 2. MONITOR SERVICE STATUS
section("2. MONITOR SERVICE STATUS")
print(run("sudo systemctl status pokemon-monitor-v2 --no-pager -l 2>/dev/null || systemctl status pokemon-monitor-v2 --no-pager -l"))

# 3. PROCESSES — monitor + chrome + top CPU
section("3. PROCESSES — monitor PIDs, Chrome count, top CPU consumers")
print("--- Monitor processes ---")
print(run("ps aux | grep -E '(python3.*main|monitor-fast|monitor-slow|monitor-nodriver|monitor-engine)' | grep -v grep"))
print()
print("--- Chrome/Chromium count ---")
chrome_count = run("pgrep -c -f 'chrom' 2>/dev/null || echo 0")
print(f"Chrome processes: {chrome_count}")
print()
print("--- Top 15 CPU consumers ---")
print(run("ps aux --sort=-%cpu | head -16"))
print()
print("--- Top 15 RAM consumers ---")
print(run("ps aux --sort=-%mem | head -16"))

# 4. MONITOR LOGS — last 30 min
section("4. LOGS — last 30 min summary")
logs = run("journalctl -u pokemon-monitor-v2 --since '30 min ago' --no-pager 2>/dev/null")
if not logs or "No entries" in logs:
    logs = run("journalctl -u pokemon-monitor-v2 -n 200 --no-pager 2>/dev/null")

if logs:
    lines = logs.split('\n')
    print(f"Total log lines (30min): {len(lines)}")
    
    # Count scan successes and errors
    ok_scans = [l for l in lines if 'produktow' in l.lower() or 'products' in l.lower()]
    errors = [l for l in lines if 'ERROR' in l or 'error' in l.upper()]
    timeouts = [l for l in lines if 'Timeout' in l or 'TIMEOUT' in l]
    warnings = [l for l in lines if 'WARNING' in l or 'warning' in l.upper()]
    
    print(f"Successful scans: {len(ok_scans)}")
    print(f"Errors: {len(errors)}")
    print(f"Timeouts: {len(timeouts)}")
    print(f"Warnings: {len(warnings)}")
    
    # Extract scan times per shop
    print("\n--- Scan times (from logs) ---")
    scan_times = {}
    for l in ok_scans:
        m = re.search(r'\[(\S+)\]\s+(\d+)\s+produkt\S*\s+w?\s*([\d.]+)s', l)
        if m:
            shop, count, stime = m.group(1), m.group(2), m.group(3)
            if shop not in scan_times:
                scan_times[shop] = []
            scan_times[shop].append((int(count), float(stime)))
    
    # Also match format without "w" (NODRIVER style: "X produktow")
    for l in ok_scans:
        m = re.search(r'\[(\S+)\]\s+(\d+)\s+produkt', l)
        if m and m.group(1) not in scan_times:
            shop = m.group(1)
            if shop not in scan_times:
                scan_times[shop] = []
            scan_times[shop].append((int(m.group(2)), 0))
    
    if scan_times:
        # Sort by avg time descending
        sorted_shops = sorted(scan_times.items(), key=lambda x: sum(t for _,t in x[1])/len(x[1]) if x[1] else 0, reverse=True)
        print(f"\n{'Shop':<25} {'Scans':<7} {'Avg time':<10} {'Products':<10}")
        print("-" * 55)
        for shop, times in sorted_shops[:40]:
            avg_time = sum(t for _, t in times) / len(times) if times else 0
            avg_prod = sum(p for p, _ in times) / len(times) if times else 0
            scan_count = len(times)
            if avg_time > 0:
                print(f"{shop:<25} {scan_count:<7} {avg_time:<10.1f}s {avg_prod:<10.0f}")
            else:
                print(f"{shop:<25} {scan_count:<7} {'N/A':<10} {avg_prod:<10.0f}")
    
    # Show last 10 errors
    if errors:
        print(f"\n--- Last 10 errors ---")
        for e in errors[-10:]:
            # Trim to 150 chars
            print(e[:150])
    
    # Show last 5 timeouts
    if timeouts:
        print(f"\n--- Last 5 timeouts ---")
        for t in timeouts[-5:]:
            print(t[:150])
    
    # Show startup messages (if recent restart)
    startups = [l for l in lines if 'starting' in l.lower() or 'Started' in l or 'shops active' in l.lower() or 'process starting' in l.lower()]
    if startups:
        print(f"\n--- Startup messages ---")
        for s in startups[-10:]:
            print(s[:150])
else:
    print("NO LOGS FOUND (journalctl empty)")

# 5. PROXY STATUS
section("5. PROXY — live test all 3 paths")
print("--- HTTP Tunnel (127.0.0.1:8888) ---")
print(run("curl -s -o /dev/null -w 'HTTP %{http_code} in %{time_total}s' --proxy http://127.0.0.1:8888 --max-time 8 https://api.ipify.org 2>&1 && echo ' IP:' && curl -s --proxy http://127.0.0.1:8888 --max-time 8 https://api.ipify.org"))
print()
print("--- Tailscale Direct (100.127.72.24:8888) ---")
print(run("curl -s -o /dev/null -w 'HTTP %{http_code} in %{time_total}s' --proxy http://100.127.72.24:8888 --max-time 8 https://api.ipify.org 2>&1 && echo ' IP:' && curl -s --proxy http://100.127.72.24:8888 --max-time 8 https://api.ipify.org"))
print()
print("--- SOCKS5 (127.0.0.1:1080) ---")
print(run("curl -s -o /dev/null -w 'HTTP %{http_code} in %{time_total}s' --socks5-hostname 127.0.0.1:1080 --max-time 8 https://api.ipify.org 2>&1 && echo ' IP:' && curl -s --socks5-hostname 127.0.0.1:1080 --max-time 8 https://api.ipify.org"))
print()
print("--- VPS Direct IP ---")
print(run("curl -s --max-time 5 https://api.ipify.org"))

# 6. CF BRIDGE / FLARESOLVERR
section("6. CF BRIDGE + FLARESOLVERR")
print("--- CF Bridge (localhost:8191) ---")
print(run("curl -s --max-time 5 http://localhost:8191/health 2>/dev/null || curl -s --max-time 5 http://localhost:8191/ 2>/dev/null || echo 'NOT RESPONDING'"))
print()
print("--- FlareSolverr Docker ---")
print(run("docker ps --filter name=flaresolverr --format '{{.Names}} {{.Status}} {{.Size}}' 2>/dev/null || echo 'docker not available or FS not running'"))

# 7. CRONTAB
section("7. CRONTAB")
print(run("crontab -l 2>/dev/null || echo 'no crontab'"))

# 8. DISK
section("8. DISK USAGE")
print(run("df -h / /opt"))
print()
print("--- Data dir ---")
print(run("ls -lah /opt/pokemon-monitor-v2/data/ 2>/dev/null | head -20"))

# 9. NETWORK — open connections
section("9. NETWORK — relevant ports")
print(run("ss -tlnp | grep -E '(8191|8888|1080|5432|8022)' 2>/dev/null || netstat -tlnp | grep -E '(8191|8888|1080|5432|8022)'"))

# 10. PHONE CONNECTIVITY
section("10. PHONE (Mi 9T) — ping + SSH")
print("--- Tailscale ping ---")
print(run("ping -c 2 -W 3 100.127.72.24 2>&1 | tail -3"))
print()
print("--- SSH check ---")
print(run("sshpass -p '123' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -p 8022 100.127.72.24 'uptime && pgrep -la tinyproxy && pgrep -la autossh' 2>&1 | head -10"))

# 11. POSTGRES
section("11. POSTGRESQL — quick stats")
pg_cmd = """sudo -u postgres psql -d pokemonitor -c "
SELECT 'products' as tbl, count(*) FROM products
UNION ALL
SELECT 'event_log_24h', count(*) FROM event_log WHERE ts > now() - interval '24h'
UNION ALL
SELECT 'event_log_1h', count(*) FROM event_log WHERE ts > now() - interval '1h'
;" 2>/dev/null"""
print(run(pg_cmd))
print()
# Recent events
pg_events = """sudo -u postgres psql -d pokemonitor -c "
SELECT event_type, count(*) as cnt FROM event_log WHERE ts > now() - interval '30 min' GROUP BY event_type ORDER BY cnt DESC;
" 2>/dev/null"""
print("--- Events last 30 min ---")
print(run(pg_events))

# 12. SUMMARY
section("12. QUICK HEALTH SUMMARY")
print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Chrome processes: {chrome_count}")
print(f"Log lines (30min): {len(lines) if logs else 0}")
print(f"Successful scans: {len(ok_scans) if logs else 'N/A'}")
print(f"Errors: {len(errors) if logs else 'N/A'}")
print(f"Timeouts: {len(timeouts) if logs else 'N/A'}")
print(f"Unique shops scanned: {len(scan_times) if logs else 'N/A'}")

print("\n=== END DIAGNOSTICS ===")
