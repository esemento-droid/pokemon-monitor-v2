# Session Context — 2026-08-18 v4 (Diagnostyka + Chrome Fix)

## ZASTĘPUJE: SESSION_CONTEXT_2026-08-18_v3.md

---

## ⚠️ OBOWIĄZKOWE NA START KAŻDEJ NOWEJ SESJI

**Po zapoznaniu się z repo, PIERWSZA RZECZ to dać userowi komendę diagnostyczną:**

```
cd /opt/pokemon-monitor-v2 && bash infra/live_report.sh && curl -sF 'file=@/tmp/live_report.txt' https://paste.rs
```

Ten raport daje PEŁNY obraz systemu w jednym shot:
- System (load, RAM, CPU)
- Chrome procesów + trend (rośnie/maleje)
- NODRIVER heals (kto spamuje Chrome)
- Per-scraper tabela (scany, czasy, errory)
- Proxy test (3 paths)
- Błędy, timeouty per shop
- DB events
- Phone status
- Podsumowanie jednolinijkowe

**NIE twórz nowych skryptów diagnostycznych. Ten istnieje i działa.**

---

## Co zrobiono w tej sesji:

### 1. Skrypt diagnostyczny — infra/live_report.sh
- Stworzony od zera, pushowany do repo
- 14+ sekcji pełnej diagnostyki systemu
- Fix: awk mawk compatibility (Debian)
- Fix: proxy test httpbin→ipify.org
- Dodane: sekcja 4a (Chrome trend), sekcja 4b (NODRIVER heals)
- Output: /tmp/live_report.txt
- Użycie: `bash infra/live_report.sh`

### 2. CF Solver — Context Pool (KLUCZOWY FIX)
- **Problem**: cf_solver.py tworzył new_context() + context.close() na KAŻDY request (37×/min)
- Każdy new_context() = nowy Chrome renderer process = Chrome rósł z 32 do 54 w 9 minut
- **Fix**: Pool 2 persistent contextów tworzonych raz. solve() otwiera PAGE w istniejącym context, zamyka PAGE (nie context). Zero nowych rendererów.
- Plik: cf_solver.py

### 3. NODRIVER heal limit
- **Problem**: heal_page() tworzył nowy context przy KAŻDYM timeout. Spirala Chrome.
- **Fix** (main.py _persistent_shop_worker):
  - Timeout → najpierw page.reload() (tani, zero nowych procesów)
  - Reload fail → heal_page() MAX 3 razy
  - Po 3 healach → cooldown 30 min (zero nowych)
  - Udany scan → reset heal counter
- Pliki: main.py, browser_manager.py

### 4. SCAN_TIMEOUT dynamiczny
- Stealth shops: 120s
- Standard shops: 90s

### 5. mediaexpert — scan_with_page dodany
- Teraz skanuje (avg 84.7s, 15 produktów)

### 6. MAX_CONCURRENT cf_solver: 6→2

### 7. NODRIVER logi z czasem
- Logi teraz: `[shop] N produktow w Xs`

### 8. Discord Router — heartbeat fix
- Pattern "shops active" → kanał heartbeat

---

## Stan systemu po sesji (15:58 2026-08-18):

| Metryka | Wartość |
|---------|---------|
| Load avg | 7.35 / 7.57 / 7.84 |
| RAM free | 1.3 GB |
| Chrome | 50 procesów (powinno spaść po context pool) |
| Scany/h | 9777 |
| Error rate | 0.7% |
| Timeout rate | 2.0% |
| Shops OK | 101 |
| Phone | ✅ ping 32ms |
| DB | 12,197 products |

---

## Architektura (po tej sesji):

```
main.py (supervisor — 5 processes)
├── FAST-1 (~59 shopów) — asyncio/aiohttp
├── FAST-2 (~59 shopów) — asyncio/aiohttp
├── SLOW (~28 shopów) — CF Bridge :8191 → cf_solver (CONTEXT POOL)
├── NODRIVER (11 shopów) — browser_manager (stealth + standard)
│   ├── Stealth: empik, mediaexpert, libristo, proshop, boosterpoint, tantis, bonito
│   ├── Standard: wilczek, dragonus, piwniczaki, rgfk, strefamarzen
│   ├── SCAN_TIMEOUT: stealth=120s, standard=90s
│   ├── Heal: reload → max 3 heals → 30min cooldown
│   └── Logi z czasem
└── ENGINES (1: tcgumisia_proxy_poller)
```

---

## Triggery (BEZ ZMIAN):
kartexpol, tantis, empik, smyk, japancollectibles, jc_30th, mediaexpert, strefatcg (max 1501 PLN), tcgumisia (TYLKO ETB 30th < 410 PLN)

---

## Znane problemy:

| Problem | Status |
|---------|--------|
| Chrome stabilność | Context pool deployed — czekamy weryfikację |
| Load 7.3-7.8 | VPS-3 (52 zł) rozwiąże |
| bonito IP banned | Potrzeba Play SIM |
| price_compare.py brak import os | Do naprawy |
| Disk 82% | Monitorować |
| 6 timeout shopów bez wartości | SHOP_DISABLED rozważyć |

---

## Pliki zmienione:
- cf_solver.py, main.py, browser_manager.py, shops/mediaexpert.py
- infra/live_report.sh (NOWY), discord_router/router.py

---

## VPS/Proxy:
- VPS: 146.59.45.228, OVH Debian, 4c/8GB
- Phone: 100.127.72.24, SSH 8022, pass 123
- Mobile IP: 37.47.130.139 (Orange PL, static)
- Orange: 800 GB/30 zł — wystarczy
- DB: postgresql://pokemonitor:mon2026pg@localhost/pokemonitor
