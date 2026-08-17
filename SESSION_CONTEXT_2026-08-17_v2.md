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
