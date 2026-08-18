# Session Context — 2026-08-18 (Morning Session: Fixes + Limango Overhaul)

## UWAGA: Ten plik zastępuje SESSION_CONTEXT_2026-08-17_v2.md

---

## Co zrobiono 2026-08-18 rano:

### 1. Strefatcg trigger — WYŁĄCZONY (URGENT!)
- **Problem**: Bot zamówił zestaw za 1750 PLN gdy max powinno być 1510
- **Root cause**: `except (ValueError, TypeError): pass` — gdy cena nie parsowała → skipował sprawdzenie → kupował za dowolną cenę!
- **Fix**: `pass` → `return` (bezpieczeństwo: nie kupuj jeśli nie możesz zweryfikować ceny)
- **Max price**: 1580 → **1510 PLN**
- **Status**: WYŁĄCZONY w detector.py (wszystkie 3 wywołania + flush zakomentowane)
- **Włączenie**: TYLKO na wyraźną prośbę usera

### 2. FlareSolverr — bumped do 768MB
- 512MB powodowało "tab crashed" na gralnia/dystryktzero
- Teraz 768MB + 1GB swap
- BROWSER_TIMEOUT=60000 (zamyka idle sesje)

### 3. Broken scrapers — diagnostyka
- **xjoy**: DZIAŁA (był w cooldown po wczorajszym RAM crash) ✅
- **mediaexpert**: DZIAŁA (był w cooldown) ✅
- **rgfk**: Anubis challenge timeout — zmniejszono timeout 90→30s, graceful failure
- **am76**: Rate-limited na VPS IP — dodano mobile proxy + delay 3s
- **gralnia/dystryktzero**: FS tab crash — naprawione bumpem FS do 768MB
- **eduksiazka/mepel**: Parser empty — do dalszego debugowania

### 4. Limango LEGO — PEŁNA PRZEBUDOWA
- **Nazwy**: było z URL obrazka (bzdury), teraz z API `item["name"]` (pełne prawidłowe nazwy)
- **URL**: `/p/{goldenProductId}` dawało 404 → teraz `/shop/product/{id}` (działa, redirectuje do SEO URL)
- **Dostępność**: było `price > 0` (zawsze true) → teraz `totalStockAvailable > 0`
- **Filtr**: odrzuca ubrania (bokserki, kurtki, piżamy), akcesoria (plecaki, tornistra, pojemniki, bidony, lunch boxy, lampki), płytki baseplate
- **Matching zestawów**: klockoradar sitemap (fuzzy match nazwy → numer 5-cyfrowy)
- **Ceny promoklocki**: cache w `data/price_cache.json` (54 zestawy), odświeżany co 4h
- **Price regex**: naprawiony — promoklocki nie ma `lowPrice` w JSON-LD, format to `najniższa cena...XX,XX zł` w HTML
- **Wynik**: 77 zestawów, 50 z porównaniem cen, embedy na DC z linkami + ceną + różnicą %

### 5. Price Cache system (NOWY)
- `price_cache.py` — cron co 4h, odpytuje promoklocki via FlareSolverr
- `infra/build_price_cache_v2.sh` — bash script, restartuje FS co 5 requestów (obejście OOM)
- `data/price_cache.json` — 54 zestawów z cenami
- Limango czyta z cache INSTANT (zero FS przy skanie)
- Flow: klockoradar sitemap (nazwa→numer) → promoklocki cache (numer→cena) → embed

### 6. Stabilność po nocy — POTWIERDZONA
- Monitor: 7h+ uptime bez restartów ✅
- RAM: 4.4-4.8 GB available (stabilne) ✅
- Audit: 152 healthy / 0 struggling / 2 dead (vs wczoraj 40/66/18) ✅
- Scany: 7736/h (vs wczoraj 841/h) — 9x więcej! ✅
- memory_guard: łapie zombies co 5 min ✅
- Night IP: Orange PL UNCHANGED (potrzeba Play SIM)

---

## Pliki zmienione 2026-08-18:
- `detector.py` — strefatcg trigger DISABLED
- `strefatcg_trigger.py` — max_price 1510, safety return on parse error
- `shops/limango.py` — pełna przebudowa (nazwy, URL, dostępność, filtr, price compare)
- `shops/rgfk.py` — graceful Anubis timeout (30s)
- `shops/am76.py` — mobile proxy + delay
- `price_cache.py` — promoklocki price regex fix
- `price_compare.py` — promoklocki price regex fix + single-word match (8+ chars)
- `discord_sender.py` — usunięte live FS calls (was causing 305 errors/h)
- `infra/build_price_cache_v2.sh` — bash price fetcher z FS restart co 5 req
- `infra/fix_flaresolverr.sh` — FS bump do 768MB
- `infra/fix_scrapers.py` — broken scraper diagnostic
- `infra/test_limango_live.py` — limango live test
- `infra/test_limango_names.py` — limango name analysis
- `infra/debug_match.py` — fuzzy match debugger
- `infra/morning_check.sh` — morning health check
- `infra/full_report.sh` — full system report

---

## Stan systemu (2026-08-18 10:00):

### Monitor: ✅ active
### RAM: 4.8 GB available
### Chrome: ~40 procesów
### FlareSolverr: 234MB / 768MB
### Proxy: tunnel OK (0.44s), SOCKS5 OK (0.40s)
### Scrapery: 165 OK, 152 healthy (≥70%)
### Limango: 77 zestawów, 50 z price compare
### Price cache: 54 zestawów z promoklocki
### Strefatcg trigger: WYŁĄCZONY

---

## Crontab (debian):
```
*/5 * * * * sudo docker start flaresolverr >/dev/null 2>&1
* * * * * /opt/pokemon-monitor-v2/proxy_watchdog.sh >/dev/null 2>&1
*/5 * * * * /opt/pokemon-monitor-v2/start_socks5.sh >/dev/null 2>&1
*/3 * * * * cd /opt/pokemon-monitor-v2 && ./venv/bin/python3 health_alert.py >/dev/null 2>&1
0 * * * * cd /opt/pokemon-monitor-v2 && timeout 300 DISPLAY=:99 ./venv/bin/python3 session_warmer.py >> data/warmer.log 2>&1
0 22 * * * cd /opt/pokemon-monitor-v2 && venv/bin/python daily_stats.py >> /opt/pokemon-monitor-v2/data/daily_stats.log 2>&1
*/5 * * * * /opt/pokemon-monitor-v2/infra/memory_guard.sh
0 */4 * * * cd /opt/pokemon-monitor-v2 && ./venv/bin/python3 price_cache.py >> data/price_cache.log 2>&1
```

---

## Następne kroki:
1. **Limango webhook** — `discord_webhook_limango.txt` ma PLACEHOLDER. Embedy lecą na główny webhook → router rozdziela. Jeśli OK — zostawić. Jeśli chcesz dedykowany kanał — wstawić URL.
2. **DB constraint** — `event_log_type_check` nie ma `NEW_LISTING` — trzeba dodać ALTER TABLE
3. **Dead scrapers** — eduksiazka, mepel (parser empty), rgfk (Anubis)
4. **Play SIM** — Orange PL nie rotuje IP. Potrzeba dynamiczna SIM.
5. **Rozwój** — patrz ANALYSIS_AND_PLAN.md (SLOW→FAST migracja, API engines)

---

## Ważne adresy:
- VPS: 146.59.45.228 (OVH, Debian)
- Phone Tailscale: 100.127.72.24
- Phone SSH: port 8022, pass: 123
- Mobile IP: 37.47.130.139 (Orange PL, static)
- DB: postgresql://pokemonitor:mon2026pg@localhost/pokemonitor
- Repo: github.com/mr68pknctx/pokemon-monitor-v2

---

# Session Context — 2026-08-17 v2 (RAM Fix + Stability + Speed Optimization)

## Co zrobiono w tej sesji:

### 1. Diagnostyka RAM — znaleziono root cause
- **309 procesów Chrome** żarło 5GB RAM
- **FlareSolverr Docker 4.2GB** — bez limitu pamięci, sesje nigdy nie zamykane
- **session_warmer.py** — 2 instancje wisiały od godzin (brak timeout w cron)
- **WARP-svc** — 378MB na nieużywany serwis
- **Brak swap** — OOM killer zabijał monitor → alert "deactivating"

### 2. RAM Fix (immediate)
- FlareSolverr: restart z `--memory=512m` + `BROWSER_TIMEOUT=60000`
- session_warmer: killed + cron z `timeout 300`
- WARP: wyłączony (żaden scraper go nie używał)
- Swap 2GB utworzony
- Zombie Chrome wyczyszczone

### 3. Permanent Stability Fixes
- **main.py `nodriver_worker`**: `os.killpg(os.getpgid(proc.pid))` — zabija CAŁY process group (Chrome + renderer + gpu), nie tylko parent
- **shops/piwniczaki.py**: dodano `try/finally: await browser.close()`
- **shops/wilczek.py**: dodano `try/finally: await browser.close()`
- **shops/strefamarzen.py**: dodano `try/finally: await browser.close()`
- **shops/dragonus.py**: dodano `try/finally: await browser.close()`
- **shops/rgfk.py**: dodano `try/finally: await browser.close()`
- **session_warmer.py**: `asyncio.wait_for(warm_fn(), timeout=60)` per konto

### 4. Speed Optimization
- **TIMEOUT_NODRIVER**: 300s → 120s (żaden zdrowy shop nie potrzebuje >120s)
- **TIMEOUT_SLOW**: 180s → 120s
- **NODRIVER delay**: 90-180s → 30-60s po sukcesie (3x szybszy cykl!)
- **SLOW delay**: 45-90s → 30-60s
- **VERY_SLOW delay**: 60-120s → 45-90s
- **Smart delay**: proporcjonalny do scan time (30% scan time = rest)
- **Dead shop progressive cooldown**: 5 timeouts → 10min, 10+ → 30min

### 5. memory_guard.sh v2 (cron co 5 min)
- Kill zombie/defunct Chrome (zawsze)
- Kill orphaned Chrome (ppid=1, >5 min)
- Kill stuck session_warmer (>5 min)
- Kill orphaned patchright/playwright drivers (ppid=1, >10 min)
- Hard limit: max 60 procesów Chrome
- RAM < 500MB → restart FlareSolverr
- RAM < 200MB → kill ALL non-monitor Chrome + restart FS

### 6. Auto-classification (SHOP_GROUP)
- Nowe shopy mogą deklarować `SHOP_GROUP = "SLOW"` / `"NODRIVER"` / `"FAST"`
- main.py czyta to automatycznie — zero edycji main.py przy dodawaniu shopów
- Backward compatible — stare shopy działają bez zmian

## Wyniki:

| Metryka | Przed sesją | Po sesji |
|---------|-------------|----------|
| RAM available | 64 MB | **6.3 GB** |
| Chrome procesów | 309 | ~50 (normalne) |
| FlareSolverr | 4.2 GB (bez limitu) | 512 MB max |
| WARP | 378 MB | wyłączony |
| Swap | 0 | 2 GB |
| NODRIVER cykl | 210-480s | **60-90s** |
| SLOW cykl | 180-300s | **90-120s** |
| Monitor status | deactivating (OOM) | **stable** |

## Stan systemu po sesji:

### Proxy:
- ✅ HTTP tunnel (127.0.0.1:8888): OK, 0.52s, IP 37.47.130.139
- ✅ Tailscale direct (100.127.72.24:8888): OK, 0.44s
- ✅ SOCKS5 (127.0.0.1:1080): OK, 0.40s
- ✅ Phone (Mi 9T): uptime 10d, tinyproxy+autossh+crond OK

### Scrapery (audit z 22:10):
- 171 shopów total
- 127 unique shops OK (w ostatniej godzinie)
- 18 dead (same timeouty, 0 success w 3h)
- 66 struggling (<30% success) — WIĘKSZOŚĆ to wolne serwery po ich stronie, NIE proxy
- 40 healthy (>=70% success)

### Cron (debian):
```
*/5 * * * * sudo docker start flaresolverr >/dev/null 2>&1
* * * * * /opt/pokemon-monitor-v2/proxy_watchdog.sh >/dev/null 2>&1
*/5 * * * * /opt/pokemon-monitor-v2/start_socks5.sh >/dev/null 2>&1
*/3 * * * * cd /opt/pokemon-monitor-v2 && ./venv/bin/python3 health_alert.py >/dev/null 2>&1
0 * * * * cd /opt/pokemon-monitor-v2 && timeout 300 DISPLAY=:99 ./venv/bin/python3 session_warmer.py >> data/warmer.log 2>&1
0 22 * * * cd /opt/pokemon-monitor-v2 && venv/bin/python daily_stats.py >> /opt/pokemon-monitor-v2/data/daily_stats.log 2>&1
*/5 * * * * /opt/pokemon-monitor-v2/infra/memory_guard.sh
```

### Night IP test:
- Jeszcze NIE było nocy (test o 3:00-5:00)
- Poprzedni wynik: IP się nie zmienił (Orange PL sticky)
- Sprawdzić JUTRO rano po 5:10

## Pliki zmienione/dodane:
- `main.py` — timeouty, delay, nodriver kill, SHOP_GROUP auto-classification
- `session_warmer.py` — timeout 60s per konto
- `shops/piwniczaki.py` — try/finally browser.close()
- `shops/wilczek.py` — try/finally browser.close()
- `shops/strefamarzen.py` — try/finally browser.close()
- `shops/dragonus.py` — try/finally browser.close()
- `shops/rgfk.py` — try/finally browser.close()
- `infra/memory_guard.sh` — v2 proactive Chrome management
- `infra/ram_fix.sh` — one-time RAM cleanup
- `infra/permanent_fix.sh` — FlareSolverr BROWSER_TIMEOUT + WARP disable
- `infra/deploy_stability.sh` — safe deploy script
- `infra/proxy_diag.sh` — proxy diagnostics
- `infra/ram_hunt.sh` — RAM diagnostics
- `infra/root_cause.sh` — root cause analysis
- `infra/full_audit.sh` — comprehensive scraper audit
- `infra/monitor_status.sh` — quick status check

## Następne kroki (JUTRO):
1. **Rano** → `bash infra/night_ip_test.sh check` — czy IP się zmienił?
2. **Audit po nocy** → `bash infra/full_audit.sh` — porównanie stabilności
3. **SLOW shopów migracja** — które mogą przejść z FlareSolverr na aiohttp (10x szybciej)
4. **Dead shopów naprawa** — indywidualnie sprawdzić 18 dead shops
5. **Rozbudowa** — patrz ANALYSIS_AND_PLAN.md

## Ważne adresy:
- VPS: 146.59.45.228 (OVH, Debian)
- Phone Tailscale: 100.127.72.24
- Phone SSH: port 8022, pass: 123
- Mobile IP: 37.47.130.139 (Orange PL)
- DB: postgresql://pokemonitor:mon2026pg@localhost/pokemonitor
- Repo: github.com/mr68pknctx/pokemon-monitor-v2
