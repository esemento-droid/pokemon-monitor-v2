# TODO — Pokemon Monitor v2

## Ostatnia aktualizacja: 2026-08-15

---

## 🔴 PRIORYTET #1 — Boty Autobuy (3 sklepy)

### bookland.pl
- [x] Scraper gotowy (Magento 2 GraphQL API)
- [ ] **Zbudować autobuy bot** (GraphQL mutations: addToCart → setShipping → placeOrder)
- [ ] Test na koncie testowym
- [ ] Deploy

### bonito.pl
- [ ] **Reset mobile IP** (IP 37.47.128.183 zbanowane przez bonito)
- [ ] Automatyzacja IP reset (airplane mode toggle na telefonie)
- [ ] Po resecie: scraper (shops/bonito.py) powinien działać (patchright passes bot protection)
- [ ] Sniff API endpoints (custom platform)
- [ ] Zbudować autobuy bot
- [ ] Test + deploy

### mediaexpert.pl
- [x] Scraper działa (nodriver + proxy, 7 produktów)
- [ ] **Seller filtering** — filtruj TYLKO produkty sprzedawane przez Media Expert (nie marketplace)
- [ ] Identyfikacja selektora seller info w offer-box
- [ ] Test bot na live site (mediaexpert_autobuy.py napisany ale nietestowany)
- [ ] Dodać product IDs do WATCH_PIDS w mediaexpert_trigger.py

---

## 🟠 PRIORYTET #2 — Nowe Scrapery (lista usera z 2026-08-15)

### Potwierdzone do zbudowania:
| # | Sklep | Platforma | Uwagi |
|---|-------|-----------|-------|
| 1 | libristo.pl | ? | |
| 2 | posters.pl | CF | Cloudflare — FlareSolverr |
| 3 | plastiq.pl | ? | |
| 4 | moriqal.pl | ? | |
| 5 | eduksiazka.pl | ? | |
| 6 | loficards.pl | ? | |
| 7 | dystryktzero | ? | |
| 8 | kiddin | ? | |
| 9 | gralnia.pl | ? | |
| 10 | maginarium | ? | |
| 11 | monsteriada | ? | |
| 12 | abondegames.pl | ? | |
| 13 | archivebyx.com | ? | |
| 14 | xjoy.pl | ? | |
| 15 | mepel.pl | ? | |

### Z wcześniejszej listy (do sprawdzenia):
| # | Sklep | Platforma | Uwagi |
|---|-------|-----------|-------|
| 1 | bigcards.pl | ? | Karty kolekcjonerskie (Topps+Pokemon) |
| 2 | magicznyrynek.pl | ? | MTG + Pokemon |
| 3 | poksy.eu | ? | Pokemon kolekcjonerskie |
| 4 | pokeserwis.pl | CF | Pokemon sklep (za Cloudflare) |
| 5 | mini-figurki.pl | ? | "Sklep karty Pokemon TCG Albumy Zabawki" |
| 6 | kidozabawki.pl | ? | Zabawki na licencjach |
| 7 | 3dtoys.pl | ? | Sklep z zabawkami |
| 8 | papiernicza.pl | ? | Papierniczy |
| 9 | biurwa.pl | ? | Artykuły biurowe/szkolne |
| 10 | atakto.pl | ? | Artykuły papiernicze |

---

## 🟡 PRIORYTET #3 — API Engines (Hydra v3)

### kartexpol (Shoper)
- [ ] Zbudować engines/kartexpol_api.py
- [ ] Pattern: /webapi/rest/product-stocks (sam jak strefatcg_api.py)
- [ ] Poll interval: 5s
- [ ] Test alongside existing shops/kartexpol.py

### strefatcg (Shoper)
- [x] engines/strefatcg_api.py EXISTS (disabled)
- [ ] User wybrał BS4 scraper only — engine disabled
- [ ] Re-enable tylko na prośbę usera

### Zero-Click Checkout (API POST):
- [ ] Sellingo API: /ajax/cart/add + /ajax/order/create (tcgumisia)
- [ ] Shoper API: /webapi/rest/orders (kartexpol, strefatcg)
- [ ] Eliminacja browser overhead (HTTP 100ms vs Chrome 5s)

---

## 🟡 PRIORYTET #4 — Infrastruktura

### Automatyzacja Mobile IP Reset
- [ ] Airplane mode toggle na Android (Termux)
- [ ] Opcje: Termux:API (termux-wifi-enable), root (settings put global airplane_mode_on), Tasker+webhook, cron w Termux
- [ ] Cron every 4-6h (prevent future bans)
- [ ] **PROBLEM**: Orange PL = STATIC IP — airplane mode NIE rotuje!
- [ ] **Rozwiązanie**: Druga SIM (Play/T-Mobile prepaid ~5 PLN) = dynamiczny IP

### Parallel Account Execution
- [ ] Boty na różnych IP (VPS + mobile + Tailscale exit nodes)
- [ ] Unikanie rate-limit (tcgumisia drop: 1/4 kont kupiło bo same-IP ATC)
- [ ] Pre-warmed sessions per konto

### FlareSolverr
- [x] Docker na VPS (działa, localhost:8191)
- [x] Używany: empik, battlestash, strefamtg, sklepkleks, promoklocki
- [ ] Dodać nowe shopy z CF (posters.pl, pokeserwis.pl)

---

## 🟢 PRIORYTET #5 — Fixes & Improvements

### Universal Trigger Migration
- [x] trigger_config.json + universal_trigger.py stworzony
- [ ] Wire into detector.py (replace 9 check_* functions with single check_trigger())
- [ ] Test na jednym shopie
- [ ] NIE usuwać starych trigger files dopóki proven na live

### tcgumisia (PAUSED)
- [ ] Diagnoza problemów bota
- [ ] NIE re-enable bez explicit user request
- [ ] Backup at /opt/pokemon-monitor-v2/data/tcgumisia-disable-backup-20260813175019

### Disabled Scrapers
- [x] strefakart — DONE (WooCommerce API + proxy, FAST)
- [x] battlestash — DONE (FlareSolverr, SLOW)
- [x] strefamtg — DONE (FlareSolverr, SLOW)
- [x] mediaexpert — DONE (nodriver + proxy, NODRIVER)
- [ ] bonito — IP banned, czeka na reset

### Price Comparison (LEGO)
- [x] klockoradar.pl (no CF, works with aiohttp) — ACTIVE
- [x] promoklocki.pl via FlareSolverr — ACTIVE (sesja reusable)
- [ ] Sprawdzić stabilność (limango HEADERS z brotli łamią klockoradar)

### Snapshot Problem
- [ ] Po restarcie monitor traktuje pierwszy scan jako snapshot (silent)
- [ ] shop_state table ma snapshot_done — sprawdzić czy przeżywa restart procesu
- [ ] Rozważyć: nie resetuj snapshot_done jeśli products istnieją w DB

---

## ✅ ZROBIONE (ostatnie sesje)

### 2026-08-15:
- [x] Image fixes: 15 scraperów + weserv.nl proxy (16 shops)
- [x] Nowy scraper: sklepkleks.com (FlareSolverr, 17 sealed)
- [x] Empik exclude fix: ' jap', kollection, portfolio, binder, talia
- [x] Tcgumisia rate limit fix: disabled engine, added proxy poller
- [x] Hearts availability fix ("brak towar" → "brak")
- [x] Swiatkart availability fix + moved to FAST
- [x] Re-enabled: strefakart, battlestash, strefamtg, mediaexpert
- [x] Final: 140 shops

### 2026-08-14:
- [x] Engine crash loop fix
- [x] gryujanusza scraper
- [x] strefamarzen URL fix
- [x] Mass exclude update (103 files)
- [x] taniaksiazka LEGO routing
- [x] Image fixes: smyk, piwniczaki, pikashop

### 2026-08-13:
- [x] Tcgumisia fully paused
- [x] Empik scraper rewritten (FlareSolverr + aiohttp + regex, 177 products)
- [x] Strefatcg bot upgraded with bot_engine
- [x] Health alerts moved to stats channel

### 2026-08-12:
- [x] PostgreSQL 4 new tables (event_log, price_history, orders, shop_intel)
- [x] Cross-shop turbo mode + adaptive timing + error recovery
- [x] Universal trigger system (trigger_config.json)
- [x] Limango LEGO scraper + price comparison
- [x] Daily stats (daily_stats.py)
- [x] VPS git auth fixed
