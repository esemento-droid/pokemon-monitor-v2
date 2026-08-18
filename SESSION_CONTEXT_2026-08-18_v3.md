# Session Context — 2026-08-18 v3 (Live Fix Session)

## ZASTĘPUJE: SESSION_CONTEXT_2026-08-18_v2.md

---

## Co zrobiono w tej sesji:

### 1. FlareSolverr Docker — USUNIĘTY PERMANENTNIE
- **Problem**: FS Docker żarł 220% CPU + 978 MB RAM (95% limitu), cron go wskrzeszał co 5 min
- **Fix**: `docker stop + rm flaresolverr`, usunięta linia z crona
- **cf_bridge.py** na :8191 działa jako replacement (SLOW shopy POST-ują tam jak wcześniej na FS)
- **Efekt**: -220% CPU, -1 GB RAM

### 2. Dead shops — DISABLED
- `mycards.py` — SHOP_DISABLED (domena SSL dead)
- `pokesmart.py` — SHOP_DISABLED (domena SSL dead)
- `tcglove.py` — SHOP_DISABLED (domena SSL dead)
- `tantis_old.py` — **USUNIĘTY** (duplikat tantis.py, ten sam SHOP="tantis", odpalał trzecią przeglądarkę)
- Dodano mechanizm `SHOP_DISABLED = True` w main.py load_shops()

### 3. FAST split — 3 → 2 procesy
- **Problem**: 3 procesy FAST × 40% CPU = 120% + SLOW 37% + Chrome ~150% = load 11 na 4 rdzeniach
- **Fix**: 2 procesy FAST (mniej interpreter overhead)
- **Efekt**: -40% CPU (1 proces mniej)

### 4. NODRIVER delay — zwiększony 60-120s (było 30-60s)
- Mniej Chrome activity = więcej CPU dla FAST shopów

### 5. Triggery — POPRAWIONE do właściwego stanu:

| Trigger | Status | Uwagi |
|---------|--------|-------|
| kartexpol | ✅ AKTYWNY | |
| tantis | ✅ AKTYWNY | |
| empik | ✅ AKTYWNY | |
| smyk | ✅ AKTYWNY | |
| japancollectibles | ✅ AKTYWNY | |
| jc_30th | ✅ AKTYWNY | |
| mediaexpert | ✅ AKTYWNY | |
| **strefatcg** | ✅ AKTYWNY | max **1501 PLN**, return on parse fail |
| **tcgumisia** | ✅ AKTYWNY | **TYLKO ETB 30th < 410 PLN**, nic innego |

### 6. Diagnostyka live (infra/live_diag_full.py)
- Nowy skrypt diagnostyczny — pełna analiza systemu w jednym outputcie
- paste.rs nie działa (500/404) — output do /tmp/diag.txt + head/tail

---

## Architektura systemu (po tej sesji):

```
main.py (parent — supervisor, auto-restart)
│
├── FAST-1 (~58 shopów) ─── asyncio, aiohttp, 5-15s cykl
├── FAST-2 (~57 shopów) ─── asyncio, aiohttp, 5-15s cykl
│
├── SLOW (~28 shopów + CF Bridge :8191)
│   └── cf_bridge.py → cf_solver.py (patchright, replaces Docker FS)
│
├── NODRIVER (11 shopów — browser_manager.py)
│   ├── Stealth browser (patchright + proxy): empik, libristo, proshop, boosterpoint, tantis, bonito
│   └── Standard browser (playwright headless): wilczek, dragonus, piwniczaki, rgfk, strefamarzen
│   └── Delay: 60-120s between scans
│
└── ENGINES (1: tcgumisia_proxy_poller, 10s poll via mobile proxy)
```

**5 procesów** total (było 6). Kernel rozkłada na 4 rdzenie.

---

## Metryki live (13:40 2026-08-18):

| Metryka | Wartość |
|---------|---------|
| Load avg (1min) | ~8-9 (spadający po fixach) |
| Chrome procesów | 45 (stałe) |
| RAM free | ~4000 MB (było 697 MB!) |
| Scany/30min | 8289 (~16,500/h) |
| Errory/30min | 23 (0.3%) |
| Timeouty/30min | 125 |
| Unique shops scanned | 232 |
| FlareSolverr | USUNIĘTY |
| CF Bridge | ✅ :8191 |
| Proxy 3 paths | ✅ all OK (0.37-0.65s) |
| Phone Mi 9T | ✅ uptime 11 days |
| DB products | 12,192 |

---

## Crontab (po fixie):
```
* * * * * /opt/pokemon-monitor-v2/proxy_watchdog.sh >/dev/null 2>&1
*/5 * * * * /opt/pokemon-monitor-v2/start_socks5.sh >/dev/null 2>&1
*/3 * * * * cd /opt/pokemon-monitor-v2 && ./venv/bin/python3 health_alert.py >/dev/null 2>&1
0 * * * * cd /opt/pokemon-monitor-v2 && timeout 300 DISPLAY=:99 ./venv/bin/python3 session_warmer.py >> data/warmer.log 2>&1
0 22 * * * cd /opt/pokemon-monitor-v2 && venv/bin/python daily_stats.py >> /opt/pokemon-monitor-v2/data/daily_stats.log 2>&1
*/5 * * * * /opt/pokemon-monitor-v2/infra/memory_guard.sh
0 */4 * * * cd /opt/pokemon-monitor-v2 && ./venv/bin/python3 price_cache.py >> data/price_cache.log 2>&1
```

**UWAGA: Brak flaresolverr w cronie — to celowe!** cf_bridge go zastępuje.

---

## Znane problemy / DO ZROBIENIA:

### 🔴 Load nadal 8-9 (cel: 6-7)
- **Przyczyna**: 115 FAST shopów + 28 SLOW + 11 NODRIVER + Chrome na 4 rdzeniach = za dużo
- **Opcje**:
  - Migrować NODRIVER shopy na aiohttp (wilczek, dragonus, strefamarzen — proste strony)
  - Zwiększyć delay FAST shopów (mniej skanów = mniej CPU, ale wolniejsza detekcja)
  - Dodać drugi VPS (rozłożyć load)

### 🟠 FAST shopy czasy 28-45s (powinno 5-15s)
- **Przyczyna**: CPU competition — duże shopy (100-446 produktów) parsują BS4 pod obciążeniem
- **Efekt**: Detekcja wolniejsza niż optymalna
- **Fix**: Shared aiohttp session (mniej TCP overhead), albo zmniejszyć NODRIVER load

### 🟠 Shopy do naprawy:
- **eduksiazka, mepel** — parser zwraca 0 produktów
- **xjoy, gralnia** — CF za mocny, cf_solver nie przechodzi
- **rgfk** — Anubis challenge timeout
- **bonito** — IP banned (potrzeba Play SIM)
- **pokespot** — SSL intermittent (serwer niestabilny)

### 🟡 Plan rozwoju (z ANALYSIS_AND_PLAN.md):
1. SLOW → FAST migracja (curl -I z VPS, które nie mają CF?)
2. API engines (kartexpol Shoper /webapi/, WooCommerce)
3. Webhook multiplexing (3 webhooks = 75 msg/min)
4. Universal trigger (trigger_config.json)
5. Shared aiohttp session per FAST process
6. Play SIM dla dynamicznego IP

### 🟡 Infrastruktura:
- paste.rs nie działa (500/404) — szukać alternatywy
- Orange PL IP statyczny — nie rotuje
- Disk 81% (57/74 GB) — trzymać oko

---

## Pliki zmienione/dodane w tej sesji:
- `main.py` — FAST 3→2 procesy, SHOP_DISABLED support, NODRIVER delay 60-120s
- `detector.py` — wszystkie triggery ustawione prawidłowo
- `strefatcg_trigger.py` — MAX_PRICE = 1501
- `tcgumisia_trigger.py` — TYLKO ETB 30th < 410 PLN
- `shops/mycards.py` — SHOP_DISABLED
- `shops/pokesmart.py` — SHOP_DISABLED
- `shops/tcglove.py` — SHOP_DISABLED
- `shops/tantis_old.py` — USUNIĘTY
- `infra/live_diag_full.py` — pełna diagnostyka live
- `infra/fix_load.sh` — skrypt naprawczy (FS kill + cron clean + restart)

---

## Ważne adresy:
- VPS: 146.59.45.228 (OVH, Debian, 4 cores, 8GB RAM)
- Phone Tailscale: 100.127.72.24
- Phone SSH: port 8022, pass: 123
- Mobile IP: 37.47.130.139 (Orange PL, static!)
- DB: postgresql://pokemonitor:mon2026pg@localhost/pokemonitor
- Repo: github.com/mr68pknctx/pokemon-monitor-v2
