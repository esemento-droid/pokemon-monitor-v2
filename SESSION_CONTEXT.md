# Session Context — 2026-08-13 (evening)

## Co zrobiono w tej sesji

### 1. TCGUMISIA — ZATRZYMANA (pauza do diagnozy)
- Branch: `ops/disable-tcgumisia` (commit `85b337c`)
- **Wyłączone:** legacy scraper (main.py skip), Hydra engine (registry=[]), trigger (TCGUMISIA_ENABLED=False), autobuy process killed
- **Backup:** `/opt/pokemon-monitor-v2/data/tcgumisia-disable-backup-20260813175019`
- **Powód:** bot failował (0/3, atc_failed, login_failed, skipped) — user chce diagnozę zanim włączy
- **NIE WŁĄCZAĆ** bez wyraźnej prośby usera

### 2. PROXY — zdiagnozowane, stabilne
- Tunnel/Tailscale flappują co 15-60 min ale recovery supervisor naprawia w <1 min
- SOCKS5 nigdy nie pada (najbardziej stabilny path)
- `pokemon-proxy-recovery.service` = enabled, active
- Tailscale ping mi-9t: 36ms, IP: 37.47.128.183
- Alert Discord działa (DOWN→UP transition)

### 3. EMPIK SCRAPER — KOMPLETNIE PRZEPISANY
- Branch: `fix/empik-flaresolverr-scraper` (commit `1995ab3`)
- **Stare:** nodriver (browser, CF bypass, ~180s subprocess, broad search = 631 śmieci)
- **Nowe:** FlareSolverr + aiohttp + regex (no browser, ~43s, 177 sealed products)
- **Kategorie:** 2 URLe
  - `https://www.empik.com/bohater/pokemon/karty-kolekcjonerskie`
  - `https://www.empik.com/strefa/karty-pokemon`
- **Paginacja:** 30/stronę, max 10 stron, `?start=30`, `?start=60`...
- **Grupa:** SLOW (timeout 180s) ale custom delay **10-20s** (cykl co ~55-65s)
- **Ceny:** data-product-price + itemprop + regex (działają)
- **Obrazki:** ecsmedia.pl CDN (23/177 ma — reszta lazy-load, ale OK)
- **Exclude (71 keywords):** deck, talia, japan, korea, chinese, german, spanish, ultra pro, sleeves, album, portfolio, playmat, magazyn, figurka, puzzle, klocki, battle academy, pokopia, wizytownik...
- **Binder ZOSTAJE** (Binder Collection = sealed z boosterami)
- **Pin collection ZOSTAJE** (sealed z boosterami)
- **Trigger:** bez zmian — PID `1756071234` (First Partner #3), max 140 zł, stock=empik only

### 4. MONITOR — aktywny, 177 produktów Empik
- `pokemon-monitor-v2.service` = active
- Pokenest: 135 produktów ✅
- Hobbity: 43 produkty ✅
- Empik: 177 produktów w 42.9s ✅
- TCGUMISIA: 0 procesów ✅

## Stan techniczny

### Procesy monitora
- **FAST:** ~107 shops (HTTP/aiohttp, 5-15s delay)
- **SLOW:** ~20 shops + empik (45-90s delay, empik override 10-20s)
- **NODRIVER:** 10 shops (proshop, boosterpoint, dragonus, piwniczaki, rgfk, strefamarzen, wilczek, tantis, battlestash, bonito) — subprocess Chrome
- **ENGINES:** 0 active (tcgumisia disabled, strefatcg disabled)

### Disabled/broken shops (TODO na przyszłe sesje)
- **battlestash** — CF managed challenge blocks all automation (w NODRIVER ale fails)
- **bonito** — mobile IP banned (37.47.128.183), needs IP rotation
- **mediaexpert** — scraper exists ale disabled, needs seller filtering (only ME-own, not marketplace)
- **tcgumisia** — paused for diagnosis (bot failures)
- **strefatcg** — engine disabled, trigger disabled (bot 1750zł concern)

### FlareSolverr
- Docker: `http://localhost:8191/v1`
- Session: `empik_scraper` (reused across pages)
- Bypasses: Empik CF ✅, promoklocki.pl ✅
- ~3-5s per page request

### Git branches (on GitHub)
- `main` — production baseline
- `ops/disable-tcgumisia` — TCGUMISIA pause (deployed on VPS)
- `fix/empik-flaresolverr-scraper` — new empik scraper (deployed on VPS)
- `infra/persistent-proxy-recovery` — proxy supervisor (deployed on VPS)

## TODO na następne sesje (priorytet)

1. **DISABLED SCRAPERS — przywrócić/naprawić:**
   - bonito.pl — potrzebuje IP rotation (druga SIM Play/T-Mobile) lub nowy proxy
   - battlestash.pl — potrzebuje FlareSolverr session albo inny bypass
   - mediaexpert.pl — seller filtering (exclude marketplace), test bot
   - tcgumisia — diagnoza: dlaczego bot failuje (rate limit? IP ban? sesja?)

2. **BOOKLAND.PL** — scraper istnieje (Magento 2 GraphQL), brakuje autobuy bot

3. **API ENGINES:**
   - kartexpol (Shoper /webapi/) — ten sam pattern co strefatcg_api
   - strefatcg — engine istnieje ale disabled, przywrócić po diagnozie

4. **EMPIK uzupełnienia:**
   - Dodać 3rd source (seriesFacet jako fallback) gdyby kategorie nie łapały nowych?
   - Więcej obrazków (lazy-load problem — 23/177 ma image)

5. **PARALLEL ACCOUNT EXECUTION** — boty na różnych IP (VPS + mobile + Tailscale)

6. **FlareSolverr** — nowe scrapery na CF-blocked shops (tcg-zielona.pl)

7. **MOBILE IP ROTATION** — automatyczny airplane mode toggle (Orange = static IP, potrzeba Play/T-Mobile SIM)
