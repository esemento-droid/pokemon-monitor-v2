# Pokemon Monitor v2 — FULL STATE August 9, 2026 (13:45)

## Location & Infrastructure
- Path: /opt/pokemon-monitor-v2/ on OVHcloud VPS (8GB RAM, 4 cores, Debian)
- Python 3.11, venv at ./venv/
- Systemd: pokemon-monitor-v2.service (enabled, auto-restart)
- ExecStart: venv/bin/python3 main.py
- Environment: PYTHONUNBUFFERED=1, DISPLAY=:99, LimitNOFILE=65535
- DB: PostgreSQL localhost (user=pokemonitor, pass=mon2026pg, db=pokemonitor)
- Restart: sudo systemctl restart pokemon-monitor-v2
- Xvfb: :99 (for nodriver headless=False)
- Capsolver: in .env (backup for CF, currently unused — nodriver works)

## Architecture (MULTI-PROCESS — Aug 9 2026)
### Entry: main.py (forks 3 processes)

**FAST process** (~100 HTTP shops)
- Own asyncio event loop
- Scan 1-15s, delay 5-15s + jitter
- Max ~40 concurrent connections
- Auto-retry on "Cannot connect" (1 retry, 2-5s delay)

**SLOW process** (~20 shops)
- Own asyncio event loop
- Scan 30-120s, delay 45-120s
- Max ~10 concurrent connections
- Includes: SHOPIFY (180-300s), SLOW, VERY_SLOW shops

**NODRIVER process** (9 Chrome shops)
- Subprocess via runner.py per shop
- Each Chrome = own process, timeout 300s
- Delay: 90-180s between scans

### Why multi-process:
- Single process (130 shops) → "Cannot connect" bursts from concurrent SSL handshakes
- Multi-process: each group has OWN event loop → no interference
- Auto-restart on crash (main.py monitors child processes)

### Performance (measured):
- RAM: 1.2 GB (3.9 GB free)
- Throughput: 1270 scans / 10 min (635 OK / 5 min)
- Success rate: 97%+ (22 ERR / 5 min)
- 135 shops active
- Scales to 300+: add FAST_B process when FAST exceeds 150

### Baseline (Aug 9, 13:45):
- OK: 635 / 5 min
- ERR: 22 / 5 min
- Shops: 135
- RAM: 1.2 GB
- Nodriver: 9 shops, all OK
- Top ERR: zarc(2), pokebeast(2), lukillo(2), bastacentershop(2), alpakagra(2)

### OS tuning (applied):
- LimitNOFILE=65535 (was 1024!)
- net.core.somaxconn=8192
- net.ipv4.tcp_max_syn_backlog=8192
- net.ipv4.tcp_fin_timeout=10
- net.ipv4.ip_local_port_range=1024-65535
- net.ipv4.tcp_tw_reuse=1
- fs.file-max=500000

## Mobile Proxy (ACTIVE)
- Phone: Xiaomi, SIM Orange PL (800GB/mies)
- Termux: tinyproxy (port 8888) + sshd (port 8022) + autossh
- VPS access: 127.0.0.1:8888 (SSH tunnel)
- SSH to phone: ssh -p 2222 localhost (pass: 123)
- Mobile IP: 37.47.128.183
- Used by: empik scraper, proshop scraper, all 6 autobuy bots

## Active Auto-Buy Bots (ALL with proxy, ALL tested Aug 9)

| Bot | Method | Status | Test result |
|-----|--------|--------|-------------|
| kartexpol_autobuy | Patchright+proxy | ✅ | Autopay reached |
| strefatcg_autobuy | Patchright+proxy | ✅ | Order #2042 placed |
| japancollectibles_autobuy | Patchright+proxy | ✅ | Full flow, "Zamawiam" ready |
| smyk_autobuy | Playwright+proxy | ✅ | Discord: "TEST OK - gotowy" |
| tantis_autobuy | API+Patchright+proxy | ✅ | Payment OK, DRY RUN 1/1 |
| empik_autobuy | nodriver+proxy | ✅ | 20 accounts ready |

### Trigger → Bot mapping:
- kartexpol_trigger → kartexpol_autobuy (keywords: "30th", "30 celebration")
- strefatcg_trigger → strefatcg_autobuy (keywords: "30th", "30 celebration")
- tantis_trigger → tantis_autobuy ("first partner 3" ≤160, "30th" no limit)
- smyk_trigger → smyk_autobuy ("first partner", "illustration collection")
- empik_trigger → empik_autobuy (PID in WATCH_PIDS, stock="empik")
- japancollectibles_trigger → japancollectibles_autobuy (PID 9419 or "pakiet")
- japancollectibles_30th_trigger → batch ("30" in name)

### Accounts (shared across bots):
- esemento@gmail.com / cR!9GW#x2wqJtGw
- blackmat36@gmail.com / v2@pvDGt#ZuN3ui
- tjbtaniojuzbylo@gmail.com / P9XAfQE.SCwFq5i
- y24015411@gmail.com / huw!e.twdCmv9@B
- Test: t11008543@gmail.com / mt!cSsphud4Zhnz

## Nodriver/PW Shops (all working, Aug 9):
| Shop | Products | Time |
|------|----------|------|
| empik | 154 | ~30s |
| boosterpoint | 308 | ~20s |
| rgfk | 100 | ~14s |
| piwniczaki | 34 | ~30s |
| dragonus | 27 | ~13s |
| wilczek | 60 | ~7s |
| strefamarzen | 24 | ~12s |
| tantis | 10 | ~7s |
| proshop | 1 | ~17s |

## Key Rules
1. ONLY sealed English products — NIE single, NIE japońskie, NIE akcesoria, NIE decks
2. Przy budowie nowego scrapera: ZAWSZE raport co znalazł, potem ustalamy EXCLUDE
3. NIGDY nie usuwać/zmieniać istniejących filtrów EXCLUDE bez potwierdzenia
4. NIGDY nie rewritować działającego kodu bez potwierdzenia
5. Komendy dla Termius: dawaj jako paste.rs, wyniki też przez paste.rs
6. Nodriver shops MUST be in NODRIVER_SHOPS set in main.py

## Commands
- Restart: sudo systemctl restart pokemon-monitor-v2
- Logs: journalctl -u pokemon-monitor-v2 --since "5 min ago" --no-pager
- Test scraper: venv/bin/python3 -u runner.py SHOPNAME
- Test bot: DISPLAY=:99 timeout 180 venv/bin/python3 -u BOTNAME.py --test ...
- Git update: sudo git fetch origin && sudo git reset --hard origin/main && sudo systemctl restart pokemon-monitor-v2
- Check proxy: curl -s -o /dev/null -w "%{http_code}" --proxy http://127.0.0.1:8888 --max-time 10 "https://www.google.com"
- Full report: bash <(curl -s https://paste.rs/T4qdZ) 2>&1 | curl -s -d @- https://paste.rs/
- Rollback: sudo git reset --hard HEAD~1 && sudo systemctl restart pokemon-monitor-v2

## Session Aug 9 Summary
- Rewritten from orchestrator (subprocess per shop, 7GB RAM) to MULTI-PROCESS (3 isolated processes, 1GB RAM)
- Fixed 5 broken scrapers (pokebeast, proshop, empik, mangiusmoczejciotki, pokecollect)
- Empik: nodriver + mobile proxy = 154 products (working!)
- All 6 autobuy bots tested with real products — ALL pass full flow
- Added proxy to smyk, strefatcg, japancollectibles bots
- OS tuning: ulimit 1024→65535, TCP params optimized
- Auto-retry on "Cannot connect" — reduced errors from 55 to 7-18
- Final: 135 shops, 1.2GB RAM, 97% success rate, all bots ready
