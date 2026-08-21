# Session Context — 2026-08-21 (Mega Stability Fix + Camoufox)

## ZASTĘPUJE: SESSION_CONTEXT_2026-08-20_v4.md

---

## ⚠️ OBOWIĄZKOWE NA START KAŻDEJ NOWEJ SESJI

```
cd /opt/pokemon-monitor-v2 && bash infra/live_report.sh && curl -sF 'file=@/tmp/live_report.txt' https://paste.rs
```

---

## Co zrobiono w tej sesji (2026-08-21):

### 1. CF Solver — kompletna stabilizacja (PRs #32-#36)

| Fix | Opis |
|-----|------|
| Warmup import | `_ensure_browser` → `_ensure_browsers` (typo blokował warmup) |
| tcgzielona routing | `tcg-zielona` → `tcgzielona` w SLOW_SHOPS (shop lądował w FAST) |
| Health check | Proaktywny restart browsers co 5min jeśli ≥10 fails |
| Restart threshold | 30 → 15 consecutive fails |
| Grace period | 180s → 480s (8 min — CF solver warmup) |
| Stagger | 5-120s → 10-180s (mniej thundering herd) |
| CF_SHOPS delay | NOWY set z 90-150s delay (capacity matching: 5 req/min < solver 9/min) |
| Client timeout | 45s → 120s (wait for semaphore queue) |
| SCAN_TIMEOUT | Wszystkie CF shopy: 180s (worker nie zabije task) |

### 2. Camoufox — Firefox anti-detect (PRs #39-#41)

**TRI-PATH ARCHITECTURE:**
- Path 1: patchright + proxy (Chromium) — 6 working CF shops
- Path 2: patchright direct (Chromium) — fallback
- **Path 3: Camoufox + proxy (Firefox) — HARD_SHOPS only**

**Instalacja na VPS:**
```bash
./venv/bin/pip install "camoufox[geoip]"
./venv/bin/python3 -m camoufox fetch
```

**HARD_SHOPS** (gralnia, xjoy, battlestash) idą **PROSTO** do Camoufox — skip Chromium.
Camoufox = Firefox fork z C++ fingerprint spoofing. CF nie rozpoznaje automation.

**Znany problem:** Camoufox browser crashuje po ~1-2h ("Target page closed").
Trzeba dodać auto-restart w `_solve_with_camoufox` (TODO na następną sesję).

### 3. Disabled/Re-enabled shopy

| Shop | Status | Powód |
|------|--------|-------|
| gameover | ✅ RE-ENABLED | Hosting wrócił (2 produkty) |
| am76 | ✅ ENABLED | User insists — cooldown naturalny |
| bonito | ✅ ENABLED | User insists — IP nadal blocked, cooldown |
| bastacentershop | ✅ ENABLED | User insists — kategoria pusta, cooldown |
| proshop | ✅ ENABLED | NODRIVER (stealth) |
| archivebyx | ❌ DISABLED | Shopify, only foreign JP/KR editions |
| mycards/pokesmart/tcglove | ❌ DISABLED | Domeny martwe |

### 4. False restocks fix (PR #37)

- smyk: `MARK_MISSING_AS_OOS = False` (search niestabilny)
- pegazgry: `MARK_MISSING_AS_OOS = False` (paginacja niestabilna)

### 5. Porównywarka cen — MARTWA (PRs #43-#45)

**OVH ABUSE REPORT** — klockoradar.pl zgłosił 1200+ req/h z naszego VPS.

**Wyłączone TOTALNIE:**
- `shops/limango.py`: `HAS_PRICE_COMPARE = False` + `if False`
- `discord_sender.py`: usunięty import `price_compare`, `LEGO_SHOPS = set()`
- Cron `price_cache.py`: USUNIĘTY z crontab
- **ZERO ścieżek** do klockoradar.pl/promoklocki.pl

**Pliki `price_cache.py` i `price_compare.py` to dead code — nikt ich nie importuje.**

### 6. Playwright/Chromium binary fix

Camoufox dependency ściągnął playwright 1.60 (downgrade z 1.61).
Brakujące chromium binary doinstalowane:
```bash
./venv/bin/python3 -m playwright install chromium
```

### 7. jc-torpedo resilience (PR #32)

- Stage retry: 3 próby zamiast 1
- Fallback na direct browser (bez proxy) jeśli 0 kont staged
- Full browser restart co 10min jeśli 0 staged
- **Znany problem:** re-stage po 30min czasem failuje → 0 staged → potrzebuje restart service

---

## Stan po sesji (2h runtime):

### CF Solver — TRI-PATH:
| Shop | Path | Status | Scany/2h |
|------|------|--------|----------|
| sklepkleks | Chromium proxy | ✅ OK | 15 |
| tcgzielona | Chromium proxy | ✅ OK | 14 |
| morigal | Chromium proxy | ✅ OK | 13 |
| xjoy | **Camoufox** | ✅ OK (4 scany, potem crash) | 4 |
| gralnia | **Camoufox** | ⚠️ Crash after few scans | ~2 |
| battlestash | **Camoufox** | ⚠️ Crash | ~1 |
| mepel | Chromium proxy | ⚠️ Cooldown loop | — |
| eduksiazka | Chromium proxy | ⚠️ Cooldown loop | — |
| dystryktzero | Chromium proxy | ⚠️ Cooldown loop | — |

### Globalny:
- **148 shopów** scanning
- **30594 skanów/2h** (~15K/h)
- Error rate: 0.5%, Timeout rate: 0.3%
- Load: 4.85 na 4 cores
- Chrome: 59 procesów

---

## TODO na następną sesję:

### PRIORYTET #1: Camoufox crash recovery
- Browser crashuje po ~1-2h ("Target page, context or browser has been closed")
- Fix: w `_solve_with_camoufox`, catch exception → set `_camoufox_browser = None` → lazy re-init
- Efekt: gralnia/xjoy/battlestash będą stabilne 24/7

### PRIORYTET #2: mepel/eduksiazka/dystryktzero cooldown loop
- Solver je obsługuje (solved OK w logach) ale cooldown wchodzi bo...
- ...semaphore starvation od Camoufox (trzyma slot przez 55s per HARD_SHOP)
- Fix: Camoufox poza semaphore (osobny slot, nie blokuje Chromium shops)

### PRIORYTET #3: bonito/am76 IP unblock
- Oba nadal timeout z VPS + mobile proxy
- Opcja: puść przez Camoufox (inna fingerprint może pomóc)
- Opcja: druga SIM (Play prepaid ~5 PLN)

### PRIORYTET #4: jc-torpedo re-stage stability
- Po 30min re-stage czasem failuje → 0 staged → daemon bezużyteczny
- Potrzebuje restart service (`sudo systemctl restart jc-torpedo`)

---

## Architektura po tej sesji:

```
main.py (5 procesów)
├── FAST-1 (~59 shopów) — asyncio/aiohttp
├── FAST-2 (~59 shopów) — asyncio/aiohttp
├── SLOW (~26 shopów) — CF Bridge :8191
│   ├── CF Solver TRI-PATH:
│   │   ├── Chromium proxy (patchright): sklepkleks, tcgzielona, morigal, mepel, eduksiazka, dystryktzero
│   │   ├── Chromium direct (patchright): fallback for non-HARD
│   │   └── **Camoufox (Firefox)**: gralnia, xjoy, battlestash (DIRECT, skip Chromium)
│   ├── CF_SHOPS delay: 90-150s (capacity matching)
│   ├── Health check: co 5min (proactive restart)
│   └── Direct aiohttp: maginarium, monsteriada, flamberg, etc.
├── NODRIVER (7 shopów) — browser_manager
│   └── empik, mediaexpert, boosterpoint, strefamarzen, tantis, libristo, proshop
└── ENGINES (1: tcgumisia_proxy_poller)
```

---

## Komendy:

```bash
# Monitor
sudo systemctl restart pokemon-monitor-v2
journalctl -u pokemon-monitor-v2 --since "5 min ago" --no-pager

# CF Solver (Camoufox)
journalctl -u pokemon-monitor-v2 --since "10 min ago" --no-pager | grep "camoufox"

# JC Torpedo
sudo systemctl restart jc-torpedo
journalctl -u jc-torpedo.service --since "5 min ago" --no-pager

# Live report
bash infra/live_report.sh && curl -sF 'file=@/tmp/live_report.txt' https://paste.rs

# Deploy
cd /opt/pokemon-monitor-v2 && git stash && git pull --rebase origin main && git stash pop && ./venv/bin/python3 -c "import main" && sudo systemctl restart pokemon-monitor-v2
```

---

## Triggery (BEZ ZMIAN):
kartexpol, tantis, empik, smyk, japancollectibles, jc_30th, mediaexpert, strefatcg (max 1501 PLN), tcgumisia (ONLY ETB 30th < 410 PLN)

## Boty (BEZ ZMIAN):
- kartexpol, strefatcg, japancollectibles → PARALLEL
- JC Torpedo → active (4 konta staged, ale re-stage niestabilny)
- tantis, empik, smyk → single account
- tcgumisia → PAUSED

## PRy w tej sesji: #32–#45 (14 PRów!)
