# Historia Sesji — Pokemon Monitor v2

## Sesja 2026-08-15

### Co zrobiono:
1. **Image fixes (21 shopów)**:
   - 15 scraperów naprawionych (relative URLs, złe selektory, brak ekstrakcji)
   - 3 HTTP error fixes: bookland (403 CDN params), gameover (404 data-src), pikashop (403 hotlink)
   - weserv.nl proxy dodany do discord_sender.py dla 16 shopów

2. **Nowy scraper: sklepkleks.com**
   - FlareSolverr (CF), 17 sealed products, SLOW group
   - PrestaShop, kategoria "Karty Pokemon"
   - Exclude: labyrinth

3. **Empik exclude fix**:
   - Dodane: `" jap"` (łapie JAP na końcu nazwy), `"kollection"`, `"portfolio"`, `"binder"`, `"talia"`
   - Problem: 'jap ' z trailing space nie łapało JAP na końcu

4. **Tcgumisia rate limit fix**:
   - WYŁĄCZONY engine (3s same IP = 429 spam, powodował 56→14→0 skoków)
   - DODANY: engines/tcgumisia_proxy_poller.py (mobile IP, /pre-order only, 10s interval)
   - Teraz stabilne: 59 products

5. **Hearts availability fix**: `"brak towar"` nigdy nie matchowało → `"brak"`

6. **Swiatkart availability fix**:
   - avail_tag selector nie istniał → zawsze available=True
   - Fix: "koszyk"/"dodaj" = available, "brak"/"niedost" = unavailable
   - Przeniesiony z SLOW do FAST (5-15s)

7. **Re-enabled 4 scrapers**:
   - strefakart — przepisany na WooCommerce API + mobile proxy (FAST, 247 products)
   - battlestash — FlareSolverr (SLOW, 32 products)
   - strefamtg — FlareSolverr + filtr pokemon (SLOW, ~105 products)
   - mediaexpert — nodriver + mobile proxy (NODRIVER, 7 products)

### Stan końcowy: 140 shopów (FAST 111 + SLOW 19 + NODRIVER 10)

---

## Sesja 2026-08-14

### Co zrobiono:
1. **Engine crash loop fix** — naprawiony infinite restart loop
2. **gryujanusza scraper** — nowy scraper + price fix
3. **strefamarzen URL fix**
4. **Mass exclude update** — 103 pliki zaktualizowane o pełne exclude listy
5. **taniaksiazka LEGO routing** — produkty LEGO kierowane do kategorii 🧱
6. **Image fixes**: smyk, piwniczaki, pikashop
7. **Exclude updates**: tantis, wilczek, vanaheim, pokenest, pokeloot, panmysza

### Kluczowe decyzje:
- **NIGDY "sleeve"** (singular) — łapie "Sleeved Booster"! Używać "sleeves" (plural)
- **NIGDY "binder"** — łapie "Binder Collection"! Używać "pro-binder"
- **NIGDY sed na detector.py** — zepsuło indentację, 3 fix komendy potrzebne

### DEPLOY PENDING (nie wrzucone na VPS tego dnia):
- GitHub main ma commit 692e1c9 ale VPS NOT YET RESTARTED
- VPS ma dirty working tree (local detector.py/trigger edits)
- Pattern: git stash + pull --rebase + stash pop

---

## Sesja 2026-08-13

### Co zrobiono:
1. **TCGUMISIA fully paused**:
   - main.py skip + engine registry empty + trigger ENABLED=False + autobuy killed
   - Branch: ops/disable-tcgumisia
   - Backup: /opt/pokemon-monitor-v2/data/tcgumisia-disable-backup-20260813175019
   - NIE re-enable bez explicit user request

2. **EMPIK SCRAPER REWRITTEN**:
   - Old: nodriver (broad search, 631 junk products)
   - New: FlareSolverr + aiohttp + regex
   - 2 category URLs (bohater/pokemon/karty-kolekcjonerskie + strefa/karty-pokemon)
   - 177 sealed English products, ~43s scan, 10-20s delay
   - Branch: fix/empik-flaresolverr-scraper
   - In SLOW_SHOPS group (timeout 180s)

3. **Strefatcg bot upgraded**:
   - bot_engine (per-account browser, fingerprint, proxy routing, humanizer 12-25s)
   - Trigger: max_price 1580 PLN, 4 accounts
   - Engine (regex 3s) DISABLED — only BS4 scraper active (user decision)
   - Bot crash after POTWIERDZAM fixed (page.evaluate fails during redirect = treat as success)
   - Dedup solved by disabling engine (1 scraper = 1 trigger)

4. **Infrastructure**:
   - health_alerts moved to discord_webhook_stats.txt channel + 5min anti-spam
   - daily_stats.py channel created (📊・daily-stats)
   - Price change filter: <5 PLN AND <3% = silent

5. **Proxy**: tunnel+tailscale flap every 15-60min, recovery supervisor auto-fixes <1min

### Kluczowe problemy:
- Empik JAP exclude — 'jap ' z trailing space nie łapie JAP na końcu (naprawione w sesji 08-15)
- tcgumisia engine 429 (rate limited at 3s polling)

---

## Sesja 2026-08-12 (późna, wieczorna)

### Co zrobiono:
1. **CRITICAL BUGS FOUND AND FIXED**:
   - `dict(**os.environ, DISPLAY=':99')` crashuje gdy DISPLAY już w env (Xvfb active)
   - Fixed: `{**os.environ, 'DISPLAY': ':99'}`
   - To spowodowało że bot NIE odpalił się na live drop (30th zestaw 1750 PLN at 21:33)
   - strefatcg trigger had NO max_price check → now set to 1580 PLN
   - Trigger spammed multiple times (engine + old scraper both detect → both trigger)

2. **Intelligence upgrade deployed**:
   - Cross-shop turbo mode: restock na tcgumisia → 5-10s scan na correlated shops for 5 min
   - CORRELATED_SHOPS w detector.py
   - Adaptive timing: turbo=5-10s, normal=5-15s (FAST), error=60-120s
   - Error recovery: 10 errors → 10min cooldown, 20 errors → 30min cooldown
   - Adaptive timeout (increase 50% after timeout)

3. **Universal trigger system**:
   - trigger_config.json + universal_trigger.py
   - JSON config per-shop: match, exclude, qty, max_price, accounts, bot path
   - Hot-reloadable (60s)
   - NOT YET WIRED into detector.py

4. **PostgreSQL upgrade** — 4 new tables:
   - event_log (every event with timestamp)
   - price_history (price changes over time)
   - orders (bot purchase tracking)
   - shop_intel (per-shop intelligence)

5. **Daily stats** (daily_stats.py): cron 22:00, Discord report

6. **VPS git auth FIXED**:
   - `git config --global credential.helper '!gh auth git-credential'`
   - gh logged in as debian, git push WITHOUT sudo
   - All code synced: GitHub main = VPS main

7. **price_compare.py rebuilt**:
   - Primary: promoklocki.pl via FlareSolverr (CF bypass)
   - Fallback: klockoradar.pl sitemap fuzzy matching (11751 sets)
   - Strategy: extract set number → promoklocki direct | no number → klockoradar fuzzy → promoklocki

### Kluczowy incydent:
- **sanitize.py usunięty** → monitor crash loop na produkcji
- User WKURZONY — od tego momentu: NIGDY nie usuwaj plików bez grep -rn

---

## Sesja 2026-08-12 (dzienna)

### Co zrobiono:
1. **Limango LEGO scraper** + price comparison + Discord LEGO category
   - shops/limango.py (6 pages, ~64 sets)
   - price_compare.py (klockoradar.pl)
   - discord_router/ moved to repo
   - PR #8

2. **Discord router** moved from /opt/discord-router/ to repo discord_router/

---

## Sesja 2026-08-11

### Co zrobiono:
1. **tcgumisia_autobuy.py test**:
   - Test order #7616 placed (Mega Moonlit Tin 3szt + Mega Darkrai 2szt = 682 PLN)
   - Bug: clear_cart() only used .c-table-product__delete--desktop → fixed with 10 fallback selectors
   - Extra product (Moonlit Tin) leftover in cart from previous session

---

## Sesja 2026-08-10

### Co zrobiono:
1. **Media Expert scraper**:
   - URL: /search?query[menu_item]=&query[querystring]=pokemon+tcg
   - Selectors: .offer-box, aria-label for name, class offer-PID, price in grosze
   - 18 products found
   - TODO: seller filtering (only Media Expert-own, not marketplace)
   - Critical bug fixed: flush_strefatcg_batch() missing from detector.py
   - Bot (mediaexpert_autobuy.py) written but untested

---

## Kluczowe Incydenty & Lessons Learned

### 1. sanitize.py deletion (2026-08-12)
- **Co się stało**: Plik usunięty "przy okazji" jako "niepotrzebny"
- **Efekt**: Monitor crash loop na produkcji, user wkurzony
- **Lesson**: NIGDY nie usuwaj bez grep -rn, NIGDY nie zakładaj że coś jest niepotrzebne

### 2. strefatcg bot nie odpalił na live drop (2026-08-12, 21:33)
- **Co się stało**: dict(**os.environ, DISPLAY=':99') crash + brak max_price check
- **Efekt**: Bot nie kupił 30th zestawu za 1750 PLN
- **Lesson**: Testuj env handling, zawsze max_price guard

### 3. sed zepsuje indentację (2026-08-14)
- **Co się stało**: sed usunął '# DISABLED:' ale nie zachował spacji (24→0)
- **Efekt**: SyntaxError/IndentationError, 3 dodatkowe fix komendy
- **Lesson**: NIGDY sed na produkcyjnych .py, używaj pełnego patcha

### 4. tcgumisia 429 spam (2026-08-13/15)
- **Co się stało**: Engine polling co 3s z tego samego IP co scraper
- **Efekt**: 429 rate limit, produkty spadały 56→14→0
- **Lesson**: Osobny IP dla engine (proxy poller), nie bombarduj jednym IP

### 5. Trigger dedup problem (2026-08-12)
- **Co się stało**: Engine + old scraper oba wykrywają ten sam produkt → bot triggered 2x
- **Efekt**: Spam zamówień, wielokrotne triggery
- **Lesson**: Wyłącz engine LUB dodaj dedup (check last 5 min)

### 6. "Sleeved Booster" wycięty przez "sleeve" exclude (2026-08-14)
- **Co się stało**: Exclude "sleeve" (singular) matchuje "Sleeved Booster" = sealed produkt
- **Efekt**: Legalne produkty wycięte z monitoringu
- **Lesson**: Używaj "sleeves" (plural), testuj exclude na full product list

---

## Branches na GitHub

| Branch | Status | Opis |
|--------|--------|------|
| main | Active | Produkcja |
| ops/disable-tcgumisia | Merged | Pauza tcgumisia |
| fix/empik-flaresolverr-scraper | Merged | Nowy empik scraper |
| (various PR branches) | Merged | PRs #8-#14 |
