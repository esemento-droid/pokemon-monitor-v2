# Session Context — 2026-08-20 v4 (CF Solver Dual-Path + Proxy Routing)

## ZASTĘPUJE: SESSION_CONTEXT_2026-08-20_v3.md

---

## ⚠️ OBOWIĄZKOWE NA START KAŻDEJ NOWEJ SESJI

```
cd /opt/pokemon-monitor-v2 && bash infra/live_report.sh && curl -sF 'file=@/tmp/live_report.txt' https://paste.rs
```

---

## Co zrobiono w tej sesji (2026-08-20 v4):

### 1. DIAGNOZA: VPS IP zbanowany przez Cloudflare

- **Root cause**: VPS IP (146.59.45.228) dostał CF challenge na stronach które WCZEŚNIEJ nie miały CF (maginarium, monsteriada, strefamtg)
- **Mobile proxy IP** (37.47.130.139) działa na tych stronach (200 OK)
- **CF shopy** (gralnia, xjoy): CF challenge zarówno z VPS jak i mobile proxy
- **CF solver (headless=True)** nie przechodził Turnstile — wykrywany jako bot

### 2. FIX: Non-CF shopy → proxy routing

| Shop | Problem | Fix |
|------|---------|-----|
| maginarium | VPS IP CF-banned | Dodano `proxy="http://127.0.0.1:8888"` + direct fallback |
| monsteriada | VPS IP CF-banned | Dodano `proxy="http://127.0.0.1:8888"` + direct fallback |
| strefamtg | VPS IP CF-banned | Dodano `proxy="http://127.0.0.1:8888"` + direct fallback |

### 3. FIX: CF Solver — kompletna przebudowa

**Architektura DUAL-PATH:**
- Browser #1: patchright `headless=False` + mobile proxy (DISPLAY=:99 via Xvfb)
- Browser #2: patchright `headless=False` BEZ proxy (VPS IP) — fallback
- Semaphore: 6 slotów concurrent
- Fresh context per solve (nie pool — unikamy cookie poisoning)

**Kluczowe zmiany (na podstawie researchu Theyka/Turnstile-Solver, EzSolver):**
- `headless=False` — KRYTYCZNE, Turnstile wykrywa headless=True
- Human-like mouse click (mouse.move z jitterem, nie element.click())
- Click attempts na 2, 5, 8, 12, 18, 25, 32 sekundzie
- CF_WAIT_MAX = 40s (55s dla HARD_SHOPS)
- Post-resolve wait: sleep(2) + networkidle + retry jeśli <10K chars
- Auto-restart browser po 30 consecutive fails

**Smart routing:**
- `VPS_FIRST_SHOPS = {"gralnia", "xjoy"}` → VPS IP first, proxy fallback
- `HARD_SHOPS = {"xjoy", "gralnia", "battlestash"}` → extended timeout, NO dual attempt (nie blokuj semaphore)
- Reszta shopów → proxy first

### 4. FIX: Scraper timeouts dla hard CF shopów

| Shop | maxTimeout | HTTP timeout | SCAN_TIMEOUT |
|------|-----------|--------------|--------------|
| gralnia | 30→60s | 45→70s | 180s |
| xjoy | 30→60s | 45→70s | 180s |
| battlestash | 30→60s | 45→70s | 180s |

### 5. FIX: Semaphore starvation

- Problem: HARD_SHOPS blokują 55s × dual attempt = starve working shops
- Fix: MAX_CONCURRENT 4→6, HARD_SHOPS nie próbują fallback path

---

## Stan CF Solver po sesji:

| Shop | CF Solver Path | Status |
|------|---------------|--------|
| tcg-zielona | proxy ✅ | 152K, stabilny |
| dystryktzero | proxy ✅ | 448K, stabilny |
| mepel | proxy ✅ | 183K, stabilny |
| eduksiazka | proxy ✅ | 172K, stabilny |
| morigal | proxy ✅ | 67K, stabilny |
| sklepkleks | proxy ✅ | 123K, stabilny |
| gralnia | direct ⚠️ | Przeszedł raz (6315 chars = za mało), potem fail 55s |
| xjoy | ❌ | Oba pathy fail — IP-level block |
| battlestash | ❌ | Oba pathy fail — IP-level block |

**Bilans: 9 z 12 CF-dependent shopów naprawione (z 0 na początku sesji)**

---

## TODO na następną sesję:

### gralnia, xjoy, battlestash — opcje do rozważenia:
1. **Residential proxy rotation** — inna klasa IP (np. BrightData, SmartProxy, itp.)
2. **nodriver** zamiast patchright — inne podejście do CF bypass (EzSolver pattern)
3. **camoufox** — Firefox-based stealth browser (inna fingerprint = CF nie rozpoznaje)
4. **Akceptacja** — 3 shopy z 150+ to <2% coverage loss

### Inne:
- sklepkleks parser daje 0 produktów mimo 123K HTML — sprawdzić URL/selektory
- gralnia z direct daje 6315 chars — za mało, post-resolve wait nie wystarczył

---

## Architektura po tej sesji:

```
main.py (5 procesów)
├── FAST-1 (~57 shopów) — asyncio/aiohttp
├── FAST-2 (~57 shopów) — asyncio/aiohttp
├── SLOW (~21 shopów) — CF Bridge :8191
│   ├── CF Solver: 2 browsers (proxy + direct), headless=False, semaphore(6)
│   │   ├── WORKING (proxy): tcg-zielona, dystryktzero, mepel, eduksiazka, morigal, sklepkleks
│   │   ├── FAILING: gralnia (direct), xjoy (both), battlestash (both)
│   │   └── HARD_SHOPS: single attempt only (no dual to prevent starvation)
│   ├── Direct aiohttp+proxy: maginarium, monsteriada, blindbox, czytam, etc.
│   └── Direct aiohttp: am76, flamberg, pikashop, etc.
├── NODRIVER (6 shopów) — browser_manager
│   └── empik, mediaexpert, boosterpoint, strefamarzen, tantis, libristo
└── ENGINES (1: tcgumisia_proxy_poller)
```

---

## Pliki zmienione w tej sesji:

| Plik | Zmiana |
|------|--------|
| `cf_solver.py` | PRZEBUDOWA: dual-path, headless=False, human click, semaphore(6) |
| `shops/maginarium.py` | Proxy routing + direct fallback |
| `shops/monsteriada.py` | Proxy routing + direct fallback |
| `shops/strefamtg.py` | Proxy routing + direct fallback |
| `shops/gralnia.py` | Timeout 30→60s, SCAN_TIMEOUT=180 |
| `shops/xjoy.py` | Timeout 30→60s, SCAN_TIMEOUT=180 |
| `shops/battlestash.py` | Timeout 30→60s, SCAN_TIMEOUT=180 |
| `infra/diag_multipath.py` | NEW: multi-path connectivity diagnostic |
| `infra/check_cf_cooldown.sh` | NEW: CF cooldown analysis |
| `infra/restart_cf_solver.py` | NEW: post-deploy verification |

---

## Komendy:

```bash
# Monitor
sudo systemctl restart pokemon-monitor-v2
journalctl -u pokemon-monitor-v2 --since "5 min ago" --no-pager

# CF Solver status (co działa)
journalctl -u pokemon-monitor-v2 --since "10 min ago" --no-pager | grep "CF_SOLVER.*Solved"

# CF Solver failures
journalctl -u pokemon-monitor-v2 --since "10 min ago" --no-pager | grep "CF_SOLVER.*not resolved"

# Multi-path diagnostic (test all paths)
DISPLAY=:99 ./venv/bin/python3 infra/diag_multipath.py

# Live report
bash infra/live_report.sh && curl -sF 'file=@/tmp/live_report.txt' https://paste.rs
```

---

## Triggery (BEZ ZMIAN):
kartexpol, tantis, empik, smyk, japancollectibles, jc_30th, mediaexpert, strefatcg (max 1501 PLN), tcgumisia (ONLY ETB 30th < 410 PLN)

## Boty (BEZ ZMIAN):
- kartexpol, strefatcg, japancollectibles → PARALLEL
- JC Torpedo → active (4 konta staged)
- tantis, empik, smyk → single account
- tcgumisia → PAUSED
