# Session Context — 2026-08-20 v3 (Performance + Restock Fix)

## ZASTĘPUJE: SESSION_CONTEXT_2026-08-20_v2.md

---

## ⚠️ OBOWIĄZKOWE NA START KAŻDEJ NOWEJ SESJI

```
cd /opt/pokemon-monitor-v2 && bash infra/live_report.sh && curl -sF 'file=@/tmp/live_report.txt' https://paste.rs
```

---

## Co zrobiono w tej sesji (2026-08-20 v3):

### 1. Cooldown Reset Fix (KRYTYCZNY BUG)
- **Bug**: Po wygaśnięciu cooldownu `consecutive_err` zostawało na 20+. Jeden kolejny fail = natychmiast znowu 30-min cooldown = pętla w nieskończoność.
- **Fix**: Reset `consecutive_err=0` po wygaśnięciu cooldownu. Shop dostaje czysty start.
- **Logi potwierdzają**: `"Cooldown expired — resetting error counter (was 10)"` — działa!

### 2. CF Solver Concurrency 2→4
- 7 CF-dependent shopów walczyło o 2 sloty semaphore.
- Maginarium (30 stron sekwencyjnie!) monopolizowało solver.
- Fix: MAX_CONCURRENT=4 + maginarium/monsteriada przeniesione na direct aiohttp.

### 3. Empik Speed 85s→36s
- Sleep: start 12→8s, subsequent pages 6→3s
- MAX_PAGES: 5→3 (nowe produkty wchodzą na top z publishDesc sort)

### 4. MARK_MISSING_AS_OOS (14 shopów)
- **Problem**: Sklepy ukrywające OOS z listingów nie generowały RESTOCK alertów.
- **Fix**: Gdy produkt znika z wyników → mark available=False w DB → powrót = RESTOCK.
- **Shopy**: smyk, planetaprezent, gryujanusza, krakenshop, hearts, smakliter, stapis, juniorkurczak, lootquest, blindbox, czytam, piwniczaki, pegazgry, zaurketto
- **Wynik**: 245 restocków/24h vs 113 wcześniej (2x wzrost!)

### 5. Smyk Restock Detection + Coverage
- Dodane query: "Scarlet Violet", "pokemon booster" (więcej produktów)
- MARK_MISSING_AS_OOS = True (smyk ukrywa OOS z search)

### 6. MediaExpert SCAN_DELAY=25s
- Module-level `SCAN_DELAY` w _persistent_shop_worker (nowy feature).
- MediaExpert: 60-120s delay → 25-37s = ~3x więcej skanów/h.

### 7. Parallel Account Execution (3 boty)
- kartexpol, strefatcg, japancollectibles — `asyncio.gather` zamiast sekwencyjnej pętli.
- Każde konto na osobnym IP (proxy_router per-account routing).
- 4 konta × ~30s sekwencyjnie = ~2 min → 4 konta parallel = ~30s.

### 8. CF Audit — 2 shopy przeniesione z FlareSolverr
- **monsteriada**: 108s → ~5s (strona nie ma CF!)
- **maginarium**: 114s → ~5-10s (strona nie ma CF!)
- Oba teraz: direct aiohttp + parallel fetch. Zero proxy dependency.
- CF solver obsługuje teraz TYLKO: gralnia, xjoy, dystryktzero, battlestash, sklepkleks, tcg-zielona.

### 9. Limango Exclude
- Dodane: regał, regal, szuflad, szafk, stolik, biurk, komoda, łóżk, dywan, naklejk, tapeta, zasłon, pościel, ręcznik, koc, poduszk, mata piankowa
- 38 śmieci usunięte z DB.

### 10. rotate_ip.sh Cron Usunięty
- Orange PL = static IP, airplane mode toggle nic nie zmieniał.
- Cron `0 */4 * * *` powodował proxy outages co 4h (08, 12, 16, 20:00).
- Usunięty z telefonu.

### 11. live_report.sh — "None" phantom fix
- aiohttp loguje `ssl:default [None]` — awk łapał jako shop name.
- Dodano "None", "null", "default" do ignore list.

---

## Stan systemu (po sesji):

| Metryka | Wartość |
|---------|---------|
| Shops active | 145 (OK) + 1 SICK |
| Scans/h | ~13,500 |
| Error rate | 0.4% |
| Timeout rate | 0.4% |
| Restocks/24h | **245** (było 113) |
| Chrome | 47 (malejący ✅) |
| Load | 5.5-6.0 |
| Empik scan | 36s (było 85s) |
| MediaExpert scan | 16s, delay 25-37s |
| Maginarium scan | ~5-10s (było 114s) |
| Monsteriada scan | ~5s (było 108s) |

---

## Architektura (po tej sesji):

```
main.py (5 procesów)
├── FAST-1 (~57 shopów) — asyncio/aiohttp
├── FAST-2 (~57 shopów) — asyncio/aiohttp  
├── SLOW (~21 shopów) — CF Bridge :8191 (4 concurrent slots)
│   └── CF-dependent: gralnia, xjoy, dystryktzero, battlestash, sklepkleks, tcg-zielona
│   └── Direct aiohttp: maginarium, monsteriada, am76, blindbox, czytam, etc.
├── NODRIVER (6 shopów) — browser_manager (stealth/standard)
│   ├── empik (36s), mediaexpert (16s, delay 25s), boosterpoint, strefamarzen, tantis, libristo
│   └── SCAN_DELAY: module-level override (mediaexpert=25s, others=60-120s)
└── ENGINES (1: tcgumisia_proxy_poller, 20s interval)
```

---

## Disabled shopy (6):
| Shop | Powód | Do odblokowania |
|------|-------|-----------------|
| bastacentershop | Kategoria pusta | Gdy shop wrzuci produkty |
| bonito | IP banned (VPS + mobile) | Nowa SIM (Play/T-Mobile) |
| proshop | IP blocked (ERR_TIMED_OUT) | Nowa SIM lub nowy proxy |
| mycards | Domena dead | Nigdy |
| pokesmart | Domena dead | Nigdy |
| tcglove | Domena dead | Nigdy |

---

## Boty (BEZ ZMIAN w logice, tylko parallel):
- kartexpol, strefatcg, japancollectibles → **PARALLEL** (asyncio.gather, multi-IP)
- JC Torpedo → bez zmian (już był parallel)
- tantis, empik, smyk → bez zmian (single account)
- tcgumisia → PAUSED

---

## Triggery (BEZ ZMIAN):
kartexpol, tantis, empik, smyk, japancollectibles, jc_30th, mediaexpert, strefatcg (max 1501 PLN), tcgumisia (ONLY ETB 30th < 410 PLN)

---

## Komendy:

```bash
# Monitor
sudo systemctl restart pokemon-monitor-v2
journalctl -u pokemon-monitor-v2 --since "5 min ago" --no-pager

# Torpedo  
sudo systemctl status jc-torpedo
journalctl -u jc-torpedo --since "5 min ago" --no-pager

# Live report
bash infra/live_report.sh && curl -sF 'file=@/tmp/live_report.txt' https://paste.rs
```
