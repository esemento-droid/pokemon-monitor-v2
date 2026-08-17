#!/bin/bash
# Full scraper audit — stats + deep check WITHOUT phone SSH (already checked)
cd /opt/pokemon-monitor-v2
echo "Running scraper audit..."
./venv/bin/python3 infra/scraper_stats.py 2>&1
echo ""
echo "=========================================="
echo ""
echo "Running deep check (no phone SSH)..."
# Use deep_check but skip watchdog SSH by running scraper_stats + custom analysis
./venv/bin/python3 -c "
import subprocess, re
from collections import defaultdict

result = subprocess.run(
    ['journalctl', '-u', 'pokemon-monitor-v2', '--since', '3 hours ago', '--no-pager', '-o', 'cat'],
    capture_output=True, text=True, timeout=60
)
lines = result.stdout.splitlines()

shops_success = defaultdict(int)
shops_timeout = defaultdict(int)
shops_errors = defaultdict(list)
shops_products = {}
shops_time = {}

for line in lines:
    m = re.search(r'\[(FAST|SLOW|NODRIVER|ENGINE)\].*\[(\w[\w-]*)\]\s+(\d+)\s+produkt', line)
    if m:
        shop = m.group(2)
        shops_success[shop] += 1
        shops_products[shop] = int(m.group(3))
        tm = re.search(r'w\s+([\d.]+)s', line)
        if tm: shops_time[shop] = float(tm.group(1))
        continue
    m = re.search(r'\[(\w[\w-]*)\]\s+(\d+)\s+pre-order', line)
    if m:
        shops_success[m.group(1)] += 1
        shops_products[m.group(1)] = int(m.group(2))
        continue
    m = re.search(r'^\[(\w[\w-]*)\]\s+(\d+)\s+produkt', line)
    if m:
        shop = m.group(1).lower()
        shops_success[shop] += 1
        shops_products[shop] = int(m.group(2))
        continue
    m = re.search(r'\[(FAST|SLOW|NODRIVER)\].*\[WARNING\].*\[(\w[\w-]*)\]\s+Timeout', line)
    if m:
        shops_timeout[m.group(2)] += 1
        continue
    m = re.search(r'\[(NODRIVER)\].*\[WARNING\].*\[(\w[\w-]*)\]\s+TIMEOUT', line)
    if m:
        shops_timeout[m.group(2)] += 1
        continue
    m = re.search(r'\[(FAST|SLOW|NODRIVER|ENGINE)\].*\[ERROR\].*\[(\w[\w-]*)\](.+)', line)
    if m:
        shops_errors[m.group(2)].append(m.group(3).strip()[:80])

all_shops = set(shops_success.keys()) | set(shops_timeout.keys()) | set(shops_errors.keys())

# Dead
dead = [(s, shops_timeout[s]) for s in all_shops if shops_success.get(s,0)==0 and shops_timeout.get(s,0)>0]
dead.sort(key=lambda x: x[1], reverse=True)

# Struggling
struggling = []
for s in all_shops:
    ok = shops_success.get(s,0)
    to = shops_timeout.get(s,0)
    total = ok + to
    if total > 3 and ok > 0 and ok/total < 0.30:
        struggling.append((s, ok, to, ok/total*100))
struggling.sort(key=lambda x: x[3])

# Error-only (no success, no timeout, only errors)
error_only = [(s, shops_errors[s]) for s in shops_errors if shops_success.get(s,0)==0 and shops_timeout.get(s,0)==0]

# Healthy
healthy = [(s, shops_success[s], shops_timeout.get(s,0), shops_products.get(s,0)) for s in all_shops if shops_success.get(s,0)>0 and shops_success[s]/(shops_success[s]+shops_timeout.get(s,0))>=0.70]
healthy.sort(key=lambda x: x[1], reverse=True)

print('='*70)
print(f'  3-HOUR DEEP ANALYSIS ({len(lines)} lines, {len(all_shops)} shops)')
print('='*70)
print()
print(f'  DEAD (only timeouts, 0 success): {len(dead)}')
print(f'  ERROR-ONLY (errors, no success/timeout): {len(error_only)}')
print(f'  STRUGGLING (<30% success): {len(struggling)}')
print(f'  HEALTHY (>=70% success): {len(healthy)}')
print()

print('-'*70)
print('  DEAD SHOPS:')
print('-'*70)
for s, to in dead:
    errs = shops_errors.get(s,[])
    e = errs[-1][:60] if errs else ''
    print(f'    {s:30s} {to:3d}x timeout  {e}')

print()
print('-'*70)
print('  ERROR-ONLY SHOPS (never timed out, never succeeded):')
print('-'*70)
for s, errs in error_only:
    print(f'    {s:30s} {len(errs):2d} errors')
    for e in errs[-2:]:
        print(f'      {e[:70]}')

print()
print('-'*70)
print('  STRUGGLING SHOPS:')
print('-'*70)
for s, ok, to, rate in struggling:
    print(f'    {s:30s} {ok:2d} OK / {to:2d} timeout = {rate:.0f}%')

print()
print('-'*70)
print(f'  TOP 30 HEALTHY SHOPS (of {len(healthy)}):')
print('-'*70)
for s, ok, to, prod in healthy[:30]:
    t = f'{shops_time[s]:.0f}s' if s in shops_time else ''
    print(f'    {s:30s} {ok:3d} scans  {prod:4d} products  {t}')
if len(healthy)>30: print(f'    ... +{len(healthy)-30} more')

# Freq
print()
print('-'*70)
print('  SCAN FREQUENCY:')
print('-'*70)
f10 = sum(1 for s in all_shops if shops_success.get(s,0)>=10)
f5 = sum(1 for s in all_shops if 5<=shops_success.get(s,0)<10)
f2 = sum(1 for s in all_shops if 2<=shops_success.get(s,0)<5)
f1 = sum(1 for s in all_shops if shops_success.get(s,0)==1)
f0 = sum(1 for s in all_shops if shops_success.get(s,0)==0)
print(f'    10+ scans/3h: {f10} shops')
print(f'    5-9 scans/3h: {f5} shops')
print(f'    2-4 scans/3h: {f2} shops')
print(f'    1 scan/3h:    {f1} shops')
print(f'    0 (dead):     {f0} shops')
print()
print('='*70)
" 2>&1
echo ""
echo "--- Night IP test check ---"
if [ -f /opt/pokemon-monitor-v2/infra/night_ip_test.sh ]; then
    bash /opt/pokemon-monitor-v2/infra/night_ip_test.sh check 2>&1
else
    echo "night_ip_test.sh not found"
fi
echo ""
echo "--- RAM/Disk ---"
free -h | head -2
echo ""
df -h / | tail -1
echo ""
echo "=== FULL AUDIT DONE ==="
