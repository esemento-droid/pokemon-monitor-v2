# Pokemon Monitor v2 — FULL STATE August 15, 2026

## 📖 Dokumentacja Projektu

Pełna dokumentacja rozbita na dedykowane pliki:

| Plik | Zawartość |
|------|-----------|
| [CONTEXT.md](CONTEXT.md) | Ten plik — quick reference, architektura, komendy |
| [HYDRA_PLAN.md](HYDRA_PLAN.md) | Plan Hydra v3 — architektura docelowa, 7 filarów, fazy budowy |
| [INFRASTRUCTURE.md](INFRASTRUCTURE.md) | VPS, PostgreSQL, mobile proxy, FlareSolverr, Discord, systemd, git |
| [BOTS.md](BOTS.md) | Boty autobuy, konta, triggery, platformy e-commerce |
| [TODO.md](TODO.md) | Pełna lista TODO z priorytetami |
| [RULES.md](RULES.md) | Krytyczne zasady pracy (NIGDY nie łamać!) |
| [SESSION_HISTORY.md](SESSION_HISTORY.md) | Historia sesji, incydenty, lessons learned |
| [SESSION_CONTEXT.md](SESSION_CONTEXT.md) | Kontekst bieżącej/ostatniej sesji |

---

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
- Mobile proxy: 127.0.0.1:8888 (HTTP) / 127.0.0.1:1080 (SOCKS5) via phone tunnel
- Szczegóły: → [INFRASTRUCTURE.md](INFRASTRUCTURE.md)

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

### Total: 145 shops in 4 independent processes

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
→ Pełne zasady: [RULES.md](RULES.md)

Quick reference:
1. **SEALED ENGLISH ONLY** — booster boxes, ETBs, tins, collections, blisters, bundles
2. **NIGDY nie edytuj działającego kodu** bez potrzeby
3. **NIGDY nie usuwaj plików** bez `grep -rn "filename" *.py`
4. **Komendy przez paste.rs** (user na Termius mobile)
5. **Pokaż listę produktów** userowi PRZED deploy
6. **EXCLUDE per-shop** (nie centralny), "sleeves" nie "sleeve", "pro-binder" nie "binder"

## Session History:
→ Pełna historia: [SESSION_HISTORY.md](SESSION_HISTORY.md)

### Latest (2026-08-16):
- Nowy scraper: tcg-zielona.pl (FlareSolverr, SLOW, 17 produktów)
- NEW_LISTING event — powiadomienia o niedostępnych nowych produktach (preorder)
- Fixy: mediaexpert URL, sklepkleks/pokespot obrazki, pokespot duplikaty
- Health alert debounce (3 fails / 9 min — koniec spamu)
- Final: **145 shops active** (FAST 115, SLOW 19, NODRIVER 10, ENGINE 1)

## Commands:
- Deploy: `cd /opt/pokemon-monitor-v2 && git fetch origin && git reset --hard origin/main && sudo systemctl restart pokemon-monitor-v2`
- Logs: `journalctl -u pokemon-monitor-v2 --since "5 min ago" --no-pager`
- Test scraper: `./venv/bin/python3 -c "import asyncio; from shops.SHOP import get_products; asyncio.run(get_products())"`
- Proxy check: `curl -s -o /dev/null -w "%{http_code}" --proxy http://127.0.0.1:8888 --max-time 10 "https://www.google.com"`

## TODO next session:
→ Pełna lista: [TODO.md](TODO.md)

Quick summary:
1. 🔴 Boty: bookland (bot), bonito (IP reset + scraper + bot), mediaexpert (seller filter + bot test)
2. 🟠 Nowe scrapery: 15 sklepów z listy usera
3. 🟡 API engines: kartexpol (Shoper)
4. 🟡 Infra: IP reset automation, parallel account execution
