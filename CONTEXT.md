# Pokemon Monitor v2 — FULL STATE August 15, 2026

## Location & Infrastructure
- Path: /opt/pokemon-monitor-v2/ on OVHcloud VPS (8GB RAM, 4 cores, Debian)
- Python 3.11, venv at ./venv/
- Systemd: pokemon-monitor-v2.service (enabled, auto-restart)
- ExecStart: venv/bin/python3 main.py
- Environment: PYTHONUNBUFFERED=1, DISPLAY=:99, LimitNOFILE=65535
- DB: PostgreSQL localhost (user=pokemonitor, pass=mon2026pg, db=pokemonitor)
- Restart: sudo systemctl restart pokemon-monitor-v2
- Xvfb: :99 (for nodriver headless=False)
- FlareSolverr: http://localhost:8191 (Docker, CF bypass)
- Discord Router: discord-router.service at /opt/pokemon-monitor-v2/discord_router/

## Architecture (MULTI-PROCESS — Aug 15 2026)
### Entry: main.py (forks 4 processes)

**FAST process** (111 HTTP shops)
- Own asyncio event loop
- Scan 1-15s, delay 5-15s + jitter
- Includes: strefakart (WooCommerce API), swiatkart (moved from SLOW for faster drops)

**SLOW process** (19 shops)
- Own asyncio event loop
- Scan 30-120s, delay 45-120s
- Includes: FlareSolverr shops (sklepkleks, battlestash, strefamtg), limango, efantasy

**NODRIVER process** (10 Chrome shops)
- Subprocess via runner.py per shop
- Each Chrome = own process, timeout 300s
- Includes: empik, proshop, boosterpoint, dragonus, piwniczaki, rgfk, strefamarzen, wilczek, tantis, mediaexpert

**ENGINES process** (1 engine)
- tcgumisia_proxy_poller: polls /pre-order via mobile proxy every 10s
- Old tcgumisia_api engine DISABLED (caused 429 spam from same IP)

### Total: 140 shops in 4 independent processes

## Mobile Proxy (ACTIVE)
- Phone: Xiaomi Mi 9T, SIM Orange PL (800GB/mies), static IP 37.47.128.183
- Termux: tinyproxy (port 8888) + sshd (port 8022) + Tailscale
- VPS access: 127.0.0.1:8888 (HTTP proxy via SSH tunnel)
- SOCKS5: 127.0.0.1:1080 (SSH -D tunnel to phone)
- Used by: empik, mediaexpert, strefakart, tcgumisia proxy poller, all autobuy bots

## Discord Image Proxy (weserv.nl)
Shops with hotlink protection/slow CDN route images through images.weserv.nl:
pikashop, bookland, gameover, basanti, cardwolf, aleplanszowki, dragoneye,
twojekarty, poketrader, missaga, karcianybunkier, magiccafe, hearts,
jaskiniatrolla, piwniczaki, sklepkleks

## Active Auto-Buy Bots:
| Bot | Method | Status |
|-----|--------|--------|
| kartexpol_autobuy | Patchright+proxy | ✅ |
| strefatcg_autobuy | Patchright+proxy | ✅ (trigger max_price 1580) |
| japancollectibles_autobuy | Patchright+proxy | ✅ |
| smyk_autobuy | Playwright+proxy | ✅ |
| tantis_autobuy | API+Patchright+proxy | ✅ |
| empik_autobuy | nodriver+proxy | ✅ |
| tcgumisia_autobuy | Patchright+proxy | ⏸️ (paused since 2026-08-13) |

## Key Rules — SCRAPER STANDARDS:
1. **SEALED ENGLISH ONLY** — booster boxes, ETBs, tins, collections, blisters, bundles
2. **DOSTĘPNOŚĆ** — testuj na live site, użyj "koszyk"/"dodaj" jako primary indicator
3. **RESTOCKI + ZMIANY CEN** — muszą działać (wykrywać przejścia available false→true)
4. **OBRAZKI NA DISCORD** — testuj HTTP HEAD, dodaj do weserv.nl proxy jeśli 403/timeout
5. **SZYBKO, STABILNIE, BEZ BANÓW** — API-first, max 6-10 req/min per shop, proxy jeśli rate limit
6. **PRODUKTY DO AKCEPTACJI** — ZAWSZE pokaż userowi listę PRZED deploy
7. **EXCLUDE KOMPLETNY** — decks, JP/KR/CHI, accessories, other games, LEGO, gry planszowe, singles
8. **FILTR CENOWY** — <10 PLN = single, wycinaj
9. **TESTUJ NA VPS** — nie sandbox (inny IP, proxy, CF)
10. **NIGDY nie edytuj istniejącego działającego kodu** bez potrzeby

## Session History:

### Session 2026-08-15:
- Image fixes: 15 scraperów + weserv.nl proxy (16 shops) + 3 HTTP error fixes
- Nowy scraper: sklepkleks.com (FlareSolverr, 17 sealed)
- Empik exclude: ' jap', kollection, portfolio, binder, talia
- Tcgumisia: wyłączony engine 3s (429), dodany proxy poller 10s (mobile IP)
- Hearts: fix availability ("brak towar" → "brak")
- Swiatkart: fix availability (avail_tag nie istniał) + moved to FAST
- Re-enabled: strefakart (API), battlestash (FlareSolverr), strefamtg (FlareSolverr), mediaexpert (nodriver)
- Final: 140 shops

### Session 2026-08-14:
- Engine crash loop fix, gryujanusza scraper, strefamarzen URL fix
- Mass exclude update (103 files), taniaksiazka LEGO routing
- Image fixes: smyk, piwniczaki, pikashop
- Bots enabled: japancollectibles + tcgumisia triggers

### Session 2026-08-13:
- Tcgumisia fully paused (bot issues)
- Empik scraper rewritten (FlareSolverr + aiohttp + regex)
- Strefatcg bot upgraded with bot_engine
- Health alerts moved to stats channel

### Session 2026-08-12:
- PostgreSQL 4 new tables (event_log, price_history, orders, shop_intel)
- Cross-shop turbo mode, adaptive timing, error recovery
- Universal trigger system (trigger_config.json)
- Limango LEGO scraper + price comparison
- Daily stats (daily_stats.py)

## Commands:
- Deploy: `cd /opt/pokemon-monitor-v2 && git fetch origin && git reset --hard origin/main && sudo systemctl restart pokemon-monitor-v2`
- Logs: `journalctl -u pokemon-monitor-v2 --since "5 min ago" --no-pager`
- Test scraper: `./venv/bin/python3 -c "import asyncio; from shops.SHOP import get_products; asyncio.run(get_products())"`
- Proxy check: `curl -s -o /dev/null -w "%{http_code}" --proxy http://127.0.0.1:8888 --max-time 10 "https://www.google.com"`

## TODO next session:
### New scrapers (user's list):
libristo.pl, plastiq.pl, moriqal.pl, eduksiazka.pl, loficards.pl, dystryktzero,
kiddin, gralnia.pl, maginarium, monsteriada, abondegames.pl, archivebyx.com,
xjoy.pl, mepel.pl, posters.pl (CF)

### Bots:
- bookland.pl — autobuy bot (scraper gotowy, Magento 2 GraphQL)
- bonito.pl — scraper + bot (IP banned, needs reset)

### Infra:
- Automatyzacja IP reset (Android airplane mode toggle)
- FlareSolverr Docker na VPS (already running)
