# Pokemon Monitor v2 — FULL STATE August 9, 2026

## Location & Infrastructure
- Path: /opt/pokemon-monitor-v2/ on OVHcloud VPS (8GB RAM, 4 cores, Debian)
- Python 3.11, venv at ./venv/
- Systemd: pokemon-monitor-v2.service (enabled, auto-restart)
- ExecStart: venv/bin/python3 main.py
- Environment: PYTHONUNBUFFERED=1, DISPLAY=:99
- DB: PostgreSQL localhost (user=pokemonitor, pass=mon2026pg, db=pokemonitor)
- Tables: products (id,shop PK), shop_state (shop PK, snapshot_done, last_scan)
- Restart: sudo systemctl restart pokemon-monitor-v2
- Xvfb: :99 (for nodriver headless=False)
- Capsolver: CAP-D8DCA0B06578EC92DB37F46DE97F5C71E69550E12DEE6C80754914E3A1EFCEFA (in .env)

## Architecture (HYBRID — Aug 9 2026)
### Entry: main.py
- **HTTP shops (120+)**: async workers in-process (1 Python process, zero overhead)
- **Nodriver/Chrome shops (9)**: subprocess via runner.py (osobny process per Chrome)
- ZERO locks, ZERO queues, ZERO waiting — każdy sklep osobno
- Shared: 1x DB pool (asyncpg, max=10), 1x Discord sender (fire-and-forget)

### Why hybrid:
- Pure in-process: Chrome instances crash each other (shared event loop, websocket conflicts)
- Pure subprocess: 130 × 60MB = OOM on 8GB (jak stary orchestrator)
- Hybrid: HTTP shops lekkie (in-process), Chrome shops ciężkie (subprocess) = ~2GB RAM total

### Timeouts:
- HTTP fast: 60s
- HTTP slow/very_slow: 180s
- Nodriver subprocess: 300s

### Delays:
- NODRIVER: 90-180s (empik, proshop, boosterpoint, dragonus, piwniczaki, rgfk, strefamarzen, wilczek, tantis)
- SHOPIFY: 180-300s (pokeloot, skladgier)
- SLOW: 45-90s (blindbox, flamberg, pikashop, paladynat, czytam, swiatkart)
- VERY_SLOW: 60-120s (efantasy, twojekarty, canislupus, tcgtrener, mangiusmoczejciotki, vanaheim, kartomaniak)
- FAST: 5-15s (everything else)
- Adaptive: if scan_time > base_delay → delay = scan_time * 1.2

### Error handling:
- 3 errors: 30-60s backoff
- 5 errors: 60-120s backoff + Discord alarm
- Heartbeat: co 6h z info o top errors

### Memory (measured Aug 9):
- Total used: ~1.2 GB (vs 7GB with old orchestrator)
- Free: 6.4 GB
- Scales to 300+ shops easily

## Mobile Proxy (ACTIVE)
- Phone: Xiaomi, SIM Orange PL (800GB/mies)
- Termux: tinyproxy (port 8888) + sshd (port 8022) + autossh (reverse tunnel)
- VPS access: proxy at 127.0.0.1:8888, SSH to phone at localhost:2222
- SSH password: 123
- Mobile IP: 37.47.128.183 (Orange Polska)
- Flow: VPS → SSH tunnel → tinyproxy on phone → internet (mobile IP)
- Also has Tailscale
- Used by: empik, proshop, kartexpol_autobuy, empik_autobuy, tantis_autobuy, smyk_autobuy, strefatcg_autobuy, japancollectibles_autobuy
- Proxy status check: curl -s -o /dev/null -w "%{http_code}" --proxy http://127.0.0.1:8888 --max-time 10 "https://httpbin.org/ip"

## Active Auto-Buy Bots (all with proxy 127.0.0.1:8888)

### 1. Kartexpol (Patchright + proxy)
- Trigger: kartexpol_trigger.py → kartexpol_autobuy.py
- Keywords: "30th", "30 celebration", "30-lecie"
- Batch mode: collects URLs, launches with --accounts 4 --qty 1
- 4 konta: esemento, blackmat36, tjbtaniojuzbylo, y24015411
- Tested: orders #328, #329 OK

### 2. Empik (nodriver + proxy)
- Trigger: empik_trigger.py → empik_autobuy.py
- Watches PID in WATCH_PIDS, price ≤ max, stock="empik"
- 20 kont: twanesek1-20@gmail.com
- Lock file prevents double-run

### 3. Strefatcg (Patchright + proxy)
- Trigger: strefatcg_trigger.py → strefatcg_autobuy.py
- Keywords: "30th", "30 celebration"
- 4 konta, batch mode

### 4. Tantis (Patchright + proxy)
- Trigger: tantis_trigger.py → tantis_autobuy.py
- Rules: "first partner 3" (≤160 zl), "30th" (no limit)
- 4 konta, batch mode

### 5. Smyk (Playwright + proxy)
- Trigger: smyk_trigger.py → smyk_autobuy.py
- Triggers on: "first partner" or "illustration collection"
- 4 konta, sequential, qty=12
- BLIK code: 654654

### 6. JapanCollectibles (Patchright + proxy)
- Trigger: japancollectibles_trigger.py → japancollectibles_autobuy.py
- PID 9419 OR "pakiet" keyword
- 4 konta

### 7. JapanCollectibles 30th (batch)
- Trigger: japancollectibles_30th_trigger.py
- "30" in name, excludes pid 9419 and "pakiet"

## Detector Logic (detector.py)
- SNAPSHOT: first scan, available products only
- NEW_PRODUCT: new pid, available → Discord + all 7 triggers
- PRICE_CHANGE: price differs (ignores "1 PLN" placeholder) → Discord + triggers
- RESTOCK: was unavailable, now available → Discord + triggers
- SOLD_OUT: was available, now unavailable → Discord only
- Batch flush at end: flush_kartexpol_batch(), flush_tantis_batch(), flush_jc_30th_batch()

## Key Technical Rules
1. Priority: REST API > WC Store API > aiohttp HTML > nodriver/Playwright
2. CF bypass: nodriver + mobile proxy + headless=False + DISPLAY=:99
3. ONLY sealed English products — NIE single, NIE japońskie, NIE akcesoria
4. Przy budowie nowego scrapera: ZAWSZE raport co znalazł, potem ustalamy EXCLUDE
5. NIGDY nie usuwać/zmieniać istniejących filtrów EXCLUDE bez potwierdzenia
6. Always fetch ALL pages (dynamic pagination detection)
7. EXCLUDE filters per shop (sleeves, albums, toploaders, etc) — NEVER change without asking
8. Scraper returns: [{id, name, price, shop, url, image, stock, available}]
9. After new scraper: add to NODRIVER_SHOPS/SLOW_SHOPS if needed, then restart
10. Discord: %20 for spaces in image URLs
11. Nodriver shops MUST be in NODRIVER_SHOPS set in main.py (subprocess routing)

## Commands (Termius quick reference)
- Restart: sudo systemctl restart pokemon-monitor-v2
- Logs live: journalctl -u pokemon-monitor-v2 -f --no-pager
- Logs errors: journalctl -u pokemon-monitor-v2 --since "5 min ago" --no-pager | grep -i "error\|timeout"
- Test scraper: venv/bin/python3 -c "import asyncio,sys;sys.path.insert(0,'/opt/pokemon-monitor-v2');from shops.NAZWA import get_products;r=asyncio.run(get_products());print(f'{len(r)} prod')"
- Test runner: venv/bin/python3 -u runner.py SHOPNAME
- Enable shop: mv shops/disabled/X.py.disabled shops/X.py
- Disable shop: mv shops/X.py shops/disabled/X.py.disabled
- Check proxy: curl -s -o /dev/null -w "%{http_code}" --proxy http://127.0.0.1:8888 --max-time 10 "https://httpbin.org/ip"
- SSH to phone: ssh -p 2222 localhost (pass: 123)
- Check RAM: free -h
- Processes: pgrep -fa "python\|chromium"
- Git update: git fetch origin && git reset --hard origin/main && sudo systemctl restart pokemon-monitor-v2

## Working with Kiro (AI instructions)
- Komendy dawaj jako paste.rs link (curl upload → user pastes bash <(curl ...) | bash)
- Wyniki z serwera: pipe do `| curl -s -d @- https://paste.rs/` → user wkleja link
- paste.rs łączy linie! Nie używaj heredoc/multiline w paste.rs
- Dla dużych zmian: push do git, user robi git pull
- NEVER rewrite working scraper from scratch — only patch what's broken
- NEVER change EXCLUDE filters without confirmation
- ALWAYS report what scraper found BEFORE adding EXCLUDE

## Scraper Contract
```python
async def get_products() -> list[dict]:
    # Returns:
    # id: "shopname_UNIQUE"
    # name: "Product Name"  
    # price: "123.45 zl" or "brak"
    # shop: "shopname"
    # url: "https://..."
    # image: "https://..."
    # stock: None or int or "empik"/"marketplace_X"
    # available: True/False
```

## Files to clean on VPS
- /opt/pokemon-monitor-v2/smyk_autobuy_guest.py (stary, zastąpiony)
- /opt/pokemon-monitor-v2/smyk_autobuy_guest2.py (stary, zastąpiony)
- /opt/pokemon-monitor-v2/smyk_autobuy_natalia.py (stary, zastąpiony)

## Session History
- Aug 3: orchestrator architecture, 109 shops, fixed OOM
- Aug 4-5: smyk bot, empik scraper, mobile proxy setup
- Aug 9: MAJOR REWRITE
  - orchestrator → HYBRID (HTTP in-process + Chrome subprocess)
  - RAM: 7GB → 1.2GB
  - Fixed 5 broken scrapers (pokebeast, proshop, empik, mangiusmoczejciotki, pokecollect)
  - Empik: 154 products via nodriver + mobile proxy (confirmed working)
  - Proshop: nodriver + mobile proxy (CF hard, testing)
  - SSL shops: added ssl=False (kantodrop, kimland, pokespot, bastacentershop)
  - All 6 autobuy bots: proxy added (smyk, strefatcg, japancollectibles were missing)
  - CONTEXT.md: rules 13-15 (sealed EN only, report before EXCLUDE, never change EXCLUDE)
  - Capsolver key added to .env (backup option for CF)
  - 131 active shops, ~1.2GB RAM, stable
