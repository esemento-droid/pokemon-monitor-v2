# Session Context — 2026-08-18 v2 (Architecture Rebuild)

## UWAGA: Ten plik zastępuje poprzedni SESSION_CONTEXT_2026-08-18

---

## Co zrobiono 2026-08-18 (cała sesja):

### 1. DIAGNOZA PROBLEMU — Load 18-22 ciągły
- **Root cause #1**: FlareSolverr Docker akumulował Chrome procesów (440 PIDs, 189% CPU, 1GB RAM)
  - FS nie zamykał sesji Chrome po użyciu → narastały w nieskończoność
  - Shopy gralnia/xjoy ciągle failowały challenge → FS retry loop → CPU spike
- **Root cause #2**: NODRIVER subprocess startował 12× Chrome jednocześnie (36 procesów)
  - Każdy subprocess (runner.py) tworzył własny Chrome, nie zamykał go po
  - start_new_session=True powodował orphany (Chrome przeżywał parent)
- **Root cause #3**: FAST process (115 shopów) na 1 rdzeniu → 62% CPU bottleneck
- **Root cause #4**: Zombie Python procesy z poprzednich restartów (37% CPU)

### 2. PRZEBUDOWA NODRIVER — Persistent Browser Architecture
- **NOWY**: `browser_manager.py` — zarządza 2 stałymi przeglądarkami
  - Stealth browser (patchright) — CF bypass, proxy, dla: empik, libristo, proshop, boosterpoint, tantis, bonito
  - Standard browser (playwright headless) — dla: wilczek, dragonus, piwniczaki, rgfk, strefamarzen
- **PRZEPISANE**: Wszystkie 11 NODRIVER shopów na `scan_with_page(page)` interface
  - Shop dostaje gotową page z browsera → navigate → parse → return
  - Browser NIGDY się nie zamyka (persistent)
  - Tab per shop żyje wiecznie (dedicated page)
  - Self-healing: page crash → heal_page() → nowa page, browser żyje
- **USUNIĘTE**: subprocess per shop, runner.py w NODRIVER, orphan Chrome problem
- **WYNIK**: NODRIVER CPU: 1.1% (było 50%+)

### 3. CF SOLVER — FlareSolverr Replacement
- **NOWY**: `cf_solver.py` — patchright-based CF challenge solver
  - 1 persistent browser, fresh tab per request, tab ZAMYKANY po solve
  - Max 6 concurrent (semaphore) vs FS unlimited (440 PIDs)
  - Zero akumulacji Chrome — tab żyje 5-20s, potem zamknięty
- **NOWY**: `cf_bridge.py` — HTTP server na localhost:8191
  - Drop-in replacement FS (ten sam POST API)
  - ZERO zmian w 10 shopach SLOW — one nadal POST'ują na :8191
  - Ale zamiast Docker FS odpowiada nasz lekki solver
- **WYNIK**: FS CPU 189% → cf_solver ~10%. FS RAM 1GB → ~100MB

### 4. FAST SPLIT — 3 niezależne procesy
- **ZMIANA**: 115 FAST shopów podzielone na 3 procesy (~38 każdy)
  - FAST-1, FAST-2, FAST-3 — osobne forki, osobne event loopy
  - Kernel rozkłada na różne rdzenie
  - Każdy ~20% CPU zamiast jednego na 62%
- **WYNIK**: Lepsze wykorzystanie 4 rdzeni, szybsze scany

### 5. Inne fixy
- Stagger startup SLOW shopów (5-120s zamiast 0-30s)
- Limango sitemap cache na dysku (nie fetch 8 XMLi per scan)
- Usunięcie battlestash z NODRIVER (był duplikatem — jest w SLOW z FlareSolverr)
- Kill zombie Python procesów z poprzednich restartów
- FlareSolverr bump do 1GB RAM (zanim zastąpiony cf_solverem)

---

## Architektura systemu (po przebudowie):

```
main.py (parent — nadzoruje, auto-restart crashy)
│
├── FAST-1 (~38 shopów HTTP) — osobny fork, osobny event loop
├── FAST-2 (~38 shopów HTTP) — osobny fork, osobny event loop
├── FAST-3 (~39 shopów HTTP) — osobny fork, osobny event loop
│   └── Każdy: async aiohttp, scan 5-15s, delay 5-15s
│
├── SLOW (20 shopów) — osobny fork + cf_bridge na :8191
│   └── CF shopy (sklepkleks, strefamtg, etc) → cf_bridge → cf_solver
│   └── Non-CF shopy (pokeloot, flamberg) → direct aiohttp
│
├── NODRIVER (11 shopów) — osobny fork + browser_manager
│   ├── Stealth browser (patchright, proxy) — empik, libristo, proshop, boosterpoint, tantis, bonito
│   ├── Standard browser (playwright headless) — wilczek, dragonus, piwniczaki, rgfk, strefamarzen
│   └── Każdy shop = stały tab, scan = page.goto() + parse, 30-60s cykl
│
└── ENGINES (API pollers) — osobny fork
    └── tcgumisia proxy poller (10s interval)
```

### Kluczowe cechy:
- **6 procesów** — kernel rozkłada na 4 rdzenie
- **Każdy niezależny** — crash/hang jednego NIE wpływa na inne
- **Zero subprocess** w NODRIVER — persistent browsers, zero orphanów
- **Zero FlareSolverr Docker** (zastąpiony cf_solver in-process)
- **Auto-restart** — parent monitoruje, crashnięty proces restartowany w 5s
- **Skalowanie**: dodaj FAST-4 przy 200+ shopach, zwiększ browser pool

---

## Metryki (po przebudowie):

| Metryka | Początek sesji | Koniec sesji |
|---------|---------------|--------------|
| Load avg | 22 | **7** |
| Scany/h | 2790 | **5730** |
| FS CPU | 189% | **1%** (Docker idle, cf_solver aktywny) |
| FS PIDs | 440 | **7** (Docker idle) |
| Chrome procesów | 57 (rosnące!) | ~61 (stałe) |
| NODRIVER CPU | 50%+ | **1.3%** |
| Timeouty/10min | 150 | **62** |
| Zombie procesy | TAK | **0** |

---

## Pliki zmienione/dodane:

### NOWE:
- `browser_manager.py` — persistent browser management (stealth + standard)
- `cf_solver.py` — patchright CF challenge solver (FS replacement)
- `cf_bridge.py` — HTTP server na :8191 (drop-in FS API)
- `infra/scan_times.sh` — raport czasów skanów
- `infra/diag_slow.sh` — diagnostyka wolnych shopów
- `infra/restart_history.sh` — historia restartów
- `infra/fix_fs_overload.sh` — restart FS z limitem
- `infra/full_system_diag.sh` — pełna diagnostyka systemu
- `infra/build_sitemap_cache.sh` — jednorazowy build sitemap cache

### ZMIENIONE:
- `main.py` — FAST split na 3 procesy, NODRIVER persistent browsers, SLOW + cf_bridge
- `shops/empik.py` — nodriver → patchright scan_with_page
- `shops/libristo.py` — nodriver → patchright scan_with_page
- `shops/proshop.py` — nodriver → patchright scan_with_page
- `shops/boosterpoint.py` — patchright → scan_with_page (pool interface)
- `shops/tantis.py` — patchright → scan_with_page (pool interface)
- `shops/bonito.py` — patchright → scan_with_page (pool interface)
- `shops/wilczek.py` — playwright → scan_with_page (pool interface)
- `shops/dragonus.py` — playwright → scan_with_page (pool interface)
- `shops/piwniczaki.py` — playwright → scan_with_page (pool interface)
- `shops/rgfk.py` — playwright → scan_with_page (pool interface)
- `shops/strefamarzen.py` — playwright → scan_with_page (pool interface)
- `shops/limango.py` — sitemap z cache dyskowego (nie fetch na żywo)
- `price_cache.py` — zapisuje sitemap cache na dysk
- `chrome_pool.py` — stary pool (legacy, zastąpiony browser_manager)

---

## Deploy na VPS:

```bash
cd /opt/pokemon-monitor-v2
git pull
docker stop flaresolverr     # Port 8191 wolny dla cf_bridge
pkill -9 -f chromium; pkill -9 -f chrome
sudo systemctl restart pokemon-monitor-v2
```

---

## Znane problemy do naprawy (następna sesja):

1. **xjoy, gralnia, battlestash** — CF challenge za mocny, cf_solver nie przechodzi (FS też nie przechodził)
2. **FAST shopy 60s avg** — wiele to wolne serwery sklepów (nie nasz problem), ale load 7 powinien pomóc
3. **eduksiazka, mepel** — parser zwraca 0 produktów (parser bug, nie CF)
4. **Chrome orphan crashpad_handler** (ppid=1) — nieszkodliwe (0% CPU) ale brudne

---

## Ważne adresy:
- VPS: 146.59.45.228 (OVH, Debian, 4 cores, 8GB RAM)
- Phone Tailscale: 100.127.72.24
- Phone SSH: port 8022, pass: 123
- Mobile IP: 37.47.130.139 (Orange PL, static)
- DB: postgresql://pokemonitor:mon2026pg@localhost/pokemonitor
- Repo: github.com/mr68pknctx/pokemon-monitor-v2
