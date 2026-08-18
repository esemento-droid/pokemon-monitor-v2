# Session Context — 2026-08-18 v5 (Chrome fix FINAL + nowe scrapery)

## ZASTĘPUJE: SESSION_CONTEXT_2026-08-18_v4.md

---

## ⚠️ OBOWIĄZKOWE NA START KAŻDEJ NOWEJ SESJI

```
cd /opt/pokemon-monitor-v2 && bash infra/live_report.sh && curl -sF 'file=@/tmp/live_report.txt' https://paste.rs
```

---

## Co zrobiono w tej sesji:

### 1. Chrome — DEFINITYWNY FIX (browser_manager.py)
- **ROOT CAUSE**: `create_page()` wywoływał `browser.new_context()` PER SHOP
  - Każdy `new_context()` = nowy Chrome renderer process
  - 11 shopów NODRIVER = 11 rendererów na start
  - Każdy `heal_page()` = kolejny renderer (nigdy nie umierał)
  - Efekt: Chrome rosnął bez końca (41→52 w 2 min)
- **FIX**: 1 shared context per browser, shopy dostają PAGE (tab) w tym samym context
  - `new_page()` = lekki tab, zero nowych procesów
  - `heal_page()` = zamknij page + nowy page w TYM SAMYM context = zero wzrostu
- **WYNIK**: Chrome stabilny ~43-50 procesów (plateau), 0 heals, trend shrinking
- **RAM**: 4.7GB → 3.0GB used (odzyskano 1.7GB!)

### 2. cf_solver.py — Proxy retry
- Dodany retry na ERR_PROXY_CONNECTION_FAILED (3s wait + 1 retry)
- Fixes: gralnia, mepel, xjoy, dystryktzero — random proxy hiccups

### 3. Timeout shopy naprawione
| Shop | Problem | Fix |
|------|---------|-----|
| zarc | timeout 15s → 32% fail | timeout 15s→30s |
| mrpuggy | sequential 27 stron, avg 131s | parallel fetch ALL pages → ~15-20s |
| mediaexpert | scan 85s vs limit 120s | sleep 12→8s, scroll 1.5→1s |
| proshop | CF timeout | SCAN_TIMEOUT=180s (module-level override) |
| bonito | Orange IP banned | BROWSER_TYPE stealth→standard (VPS IP) |

### 4. strefamtg — przeniesiony do FAST
- Site NIE MA Cloudflare (curl daje 200 + pełny HTML)
- Przepisany na direct aiohttp + parallel fetch 3 stron
- Usunięty z SLOW_SHOPS w main.py
- Wynik: ~100 skanów/h vs poprzednio 1 scan + 8 timeoutów

### 5. thepokemania.de — NOWY SCRAPER (zagraniczny)
- URL: /pokemon-tcg-sets/lingua-englisch (filtr angielskich kart)
- Method: GA4 dataLayer (ceny RON→EUR) + LD+JSON (URL) + data-src (obrazki) + BS4 grid-image--out-of-stock (dostępność)
- Pagination: 6 stron, sequential 3s delay (429 rate limit)
- Filtr: exclude Romanian (cutie), exclude DE edition (" DE " w nazwie)
- Discord routing: FOREIGN_SHOPS → 🌍 Zagraniczne
- ~220 produktów (39 avail, reszta OOS)
- Sort: OOS first, available last (Discord scroll fix)

### 6. limango — price_compare FIX
- Bug: `import os` missing → NameError → porównanie cen NIGDY nie działało
- Fix: dodany `import os` na górze pliku
- Efekt: embedy na DC pokażą 📊 Porównanie cen (promoklocki.pl) po restarcie

### 7. live_report.sh — nowy format
- Shopy pogrupowane: FAST / SLOW / NODRIVER / ENGINE
- Status: OK / SICK (>30% timeout) / DEAD (0 skanów)
- Parser: ignoruje ALL-CAPS nazwy (fix GNOM/HMS false-positive)
- Podsumowanie: SCANNING vs SICK+DEAD

### 8. main.py — module-level SCAN_TIMEOUT
- `_persistent_shop_worker` czyta `getattr(module, 'SCAN_TIMEOUT', default)`
- Shopy mogą override (proshop=180s, bonito=150s)

---

## Stan systemu po sesji:

| Metryka | Wartość |
|---------|---------|
| Scans/h | 11,703 |
| Error rate | 0.3% |
| Timeout rate | 1.1% |
| SCANNING | 141 |
| SICK+DEAD | 4 |
| Chrome | 43 (stabilny, 0 heals) |
| Load | 6.5 |
| RAM free | ~900MB |

---

## Architektura (po tej sesji):

```
main.py (supervisor — 5 processes)
├── FAST-1 (~60 shopów) — asyncio/aiohttp
│   └── strefamtg (moved from SLOW, direct aiohttp)
│   └── thepokemania (NEW, sequential 3s delay, FOREIGN)
├── FAST-2 (~60 shopów) — asyncio/aiohttp
├── SLOW (~18 shopów) — CF Bridge :8191 → cf_solver (CONTEXT POOL + PROXY RETRY)
├── NODRIVER (9 shopów) — browser_manager (SHARED CONTEXT per browser)
│   ├── Stealth: empik, mediaexpert, libristo, proshop, boosterpoint, tantis
│   ├── Standard: wilczek, dragonus, piwniczaki, strefamarzen, bonito(moved from stealth)
│   ├── SCAN_TIMEOUT: stealth=120s (proshop=180s), standard=90s (bonito=150s)
│   ├── Heal: reload → max 3 heals → 30min cooldown
│   └── 0 heals/h (shared context fix works!)
└── ENGINES (1: tcgumisia_proxy_poller)
```

---

## Triggery (BEZ ZMIAN):
kartexpol, tantis, empik, smyk, japancollectibles, jc_30th, mediaexpert, strefatcg (max 1501 PLN), tcgumisia (TYLKO ETB 30th < 410 PLN)

---

## Nowe zasady dodane do RULES.md:
1. First snapshot sort: OOS first → available last (Discord scroll)
2. Foreign shops: FOREIGN_SHOPS routing, waluta oryginalna, filtr URL
3. Architektura scraperów: module SCAN_TIMEOUT, proxy rules, NODRIVER
4. Obrazki: slug verify, ratio 1:1/2:1, data-src > src
5. Dostępność: CSS class > button text

---

## Znane problemy (remaining):

| Problem | Status |
|---------|--------|
| proshop CF block | SCAN_TIMEOUT=180s, czekamy |
| bonito | Standard browser z VPS IP (testujemy) |
| thepokemania spam | Ustabilizowane po full seed, kanał przeniesiony do 🌍 |
| limango price_compare | Naprawione, wejdzie po restarcie |
| Chrome ~43-50 | STABILNY, nie rośnie |

---

## Pliki zmienione:
- browser_manager.py (shared context — KEY FIX)
- cf_solver.py (proxy retry)
- main.py (module SCAN_TIMEOUT, strefamtg removed from SLOW)
- shops/strefamtg.py (rewrite: direct aiohttp)
- shops/thepokemania.py (NEW)
- shops/proshop.py (SCAN_TIMEOUT=180, CF wait 20+20s)
- shops/bonito.py (standard browser, VPS IP)
- shops/zarc.py (timeout 30s)
- shops/mrpuggy.py (parallel fetch)
- shops/mediaexpert.py (reduced sleeps)
- shops/limango.py (import os fix)
- discord_router/config.py (FOREIGN_SHOPS += thepokemania)
- infra/live_report.sh (grouped format, SICK/DEAD)
- infra/seed_thepokemania.sh (NEW)
- RULES.md (nowe zasady)

---

## VPS/Proxy (BEZ ZMIAN):
- VPS: 146.59.45.228, OVH Debian, 4c/8GB
- Phone: 100.127.72.24, SSH 8022, pass 123
- Mobile IP: 37.47.130.139 (Orange PL)
- DB: postgresql://pokemonitor:mon2026pg@localhost/pokemonitor
