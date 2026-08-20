# Session Context — 2026-08-20 (Diagnostic Overhaul + Scraper Fixes)

## ZASTĘPUJE: SESSION_CONTEXT_2026-08-19.md

---

## ⚠️ OBOWIĄZKOWE NA START KAŻDEJ NOWEJ SESJI

```
cd /opt/pokemon-monitor-v2 && bash infra/live_report.sh && curl -sF 'file=@/tmp/live_report.txt' https://paste.rs
```

Jeśli paste.rs nie działa (500):
```
cd /opt/pokemon-monitor-v2 && bash infra/live_report.sh && cp /tmp/live_report.txt deep_diag_output.txt && git add deep_diag_output.txt && git commit -m "diag" && git push origin main
```

---

## Co zrobiono w tej sesji:

### 1. Diagnostyka — PEŁNA PRZEBUDOWA

**live_report.sh naprawiony:**
- ENGINE proxy poller linie teraz prawidłowo liczone (było fałszywie "DEAD")
- Filtr invalid shop names z error messages (nie tworzy fake wpisów jak "Connect call failed")
- ENGINE `[tcgumisia-proxy] 70 products` → zliczane jako skany

**deep_diag.sh — NOWY (kompletna diagnostyka):**
- Konfigurowalny window: `bash infra/deep_diag.sh [HOURS]` (default 3h)
- Sekcje: System, Service PIDs, Proxy, Phone crontab, NODRIVER per-shop, ENGINE, Problem shops, Cooldowns, Heals, Timeouts, Errors, DB events, Cron, Crashes, Proxy watchdog, Summary
- Kompaktowy output (~120 linii vs 4700 w starej wersji)

### 2. Airplane Mode Cron — WYŁĄCZONY

- Skrypt `infra/disable_airplane_cron.sh` usunął z telefonu (Mi 9T) wpisy airplane/night_sleep/failsafe
- Telefon crontab teraz: watchdog (co 1 min) + rotate_ip (co 4h, skip z guardem)
- Orange PL IP jest static — airplane mode nigdy nie rotował, tylko zrywał proxy

### 3. Scrapery — PRZEPISANE / NAPRAWIONE

| Shop | Było | Jest | Metoda |
|------|------|------|--------|
| **dragonus** | NODRIVER (0 skanów, page wysychała) | ✅ FAST aiohttp + mobile proxy | Parallel page fetch, ~60 skanów/h |
| **piwniczaki** | NODRIVER (0 skanów, page wysychała) | ✅ FAST aiohttp + mobile proxy + retry | 3× retry (proxy→proxy→direct), HTML validation |
| **wilczek** | NODRIVER (0 skanów, page wysychała) | ✅ SLOW standalone patchright VPS IP | SPA wymaga JS render, headless=True |
| **bonito** | NODRIVER (bot protection failed) | ❌ SHOP_DISABLED | VPS IP + mobile IP oba zblokowane |
| **rgfk** | NODRIVER (Anubis 44× failed) | 🗑️ USUNIĘTY z repo | Anubis challenge nie do obejścia, drogi |
| **proshop** | NODRIVER (IP blocked) | Był SHOP_DISABLED | Bez zmian |
| **empik** | Obrazki = no_picture.svg | ✅ Naprawiony | `lazy-img` atrybut + weserv.nl proxy |

### 4. Empik Obrazki — NAPRAWIONE

**Root cause:** Empik używa niestandardowego atrybutu `lazy-img` na `<img class="lazy">`.
- `src` = placeholder (`no_picture.svg`)
- `lazy-img` = prawdziwy URL (`https://ecsmedia.pl/c/...`)

**Fix:**
- EXTRACT_JS: `lazy-img` > `data-src` > `data-lazy-img` > `data-original` > `srcset` > `src`
- Protocol-relative fix: `//ecsmedia.pl/...` → `https://ecsmedia.pl/...`
- Filtr `data:image` placeholderów
- Empik dodany do PROXY_SHOPS (weserv.nl bypass hotlink protection)

### 5. main.py — Zmiany

- NODRIVER_SHOPS: usunięte dragonus, piwniczaki, rgfk, wilczek, bonito (7→7 shopów: empik, mediaexpert, proshop, boosterpoint, strefamarzen, tantis, libristo)
- SLOW_SHOPS: dodany wilczek
- VERY_SLOW_SHOPS: dodany bonito
- shop_worker: respektuje module-level SCAN_TIMEOUT (getattr, jak _persistent_shop_worker)

---

## Architektura (po tej sesji):

```
main.py (supervisor — 5 processes)
├── FAST-1 (~60 shopów) — asyncio/aiohttp
│   ├── dragonus (NEW: aiohttp + mobile proxy, parallel fetch)
│   ├── piwniczaki (NEW: aiohttp + mobile proxy, retry 3×)
│   └── ... (116 total FAST shops)
├── FAST-2 (~60 shopów) — asyncio/aiohttp
├── SLOW (~20 shopów) — CF Bridge :8191 → cf_solver
│   ├── wilczek (NEW: standalone patchright VPS IP, headless)
│   ├── bonito (DISABLED — oba IP zblokowane)
│   └── ... (CF shops: battlestash, sklepkleks, tcg-zielona, etc.)
├── NODRIVER (7 shopów) — browser_manager (SHARED CONTEXT per browser)
│   ├── Stealth: empik, mediaexpert, libristo, boosterpoint, tantis
│   ├── Standard: strefamarzen
│   ├── PROSHOP: DISABLED (IP blocked)
│   ├── Empik: lazy-img fix, weserv.nl proxy for Discord
│   └── mediaexpert: HYBRID (full goto, GraphQL 404 fallback)
└── ENGINES (1: tcgumisia_proxy_poller → /pokemon + /pre-order, 20s interval)
```

---

## Stan systemu po sesji (09:20, 2026-08-20):

| Metryka | Wartość |
|---------|---------|
| Load | 4.1-4.4 |
| RAM | 3.3GB/7.7GB used (4.4GB available) |
| Chrome | 32 procesów (spadek z 39) |
| Scans/h (projekcja) | ~14,000 |
| Error rate | <0.1% |
| Timeout rate | <0.5% |
| Cooldowns | 0 |
| Heals | 0 |
| ENGINE | ✅ 485 polli/3h, 0 errors |
| Proxy 3/3 | ✅ HTTP/Tailscale/SOCKS5 |
| Phone ping | 25-47ms |

---

## Triggery (BEZ ZMIAN):
kartexpol, tantis, empik, smyk, japancollectibles, jc_30th, mediaexpert, strefatcg (max 1501 PLN), tcgumisia (ONLY ETB 30th < 410 PLN)

---

## Pliki zmienione/dodane w tej sesji:
- `shops/dragonus.py` — REWRITE: aiohttp + proxy, parallel fetch (was NODRIVER)
- `shops/piwniczaki.py` — REWRITE: aiohttp + proxy + retry (was NODRIVER)
- `shops/wilczek.py` — REWRITE: standalone patchright VPS IP headless (was NODRIVER)
- `shops/bonito.py` — SHOP_DISABLED (both IPs blocked)
- `shops/rgfk.py` — DELETED (Anubis unsolvable)
- `shops/empik.py` — lazy-img fix, protocol-relative fix, data:image filter
- `main.py` — NODRIVER_SHOPS updated, SLOW/VERY_SLOW updated, shop_worker SCAN_TIMEOUT
- `discord_sender.py` — empik added to PROXY_SHOPS (weserv.nl)
- `infra/live_report.sh` — ENGINE parsing fix, invalid shop name filter
- `infra/deep_diag.sh` — REWRITE: compact full diagnostic, configurable window
- `infra/disable_airplane_cron.sh` — NEW: removes airplane cron from phone
- `infra/test_empik_img.sh` — NEW: debug empik image attributes
- `infra/report_10h.sh` — DELETED (replaced by deep_diag.sh)
- `deep_diag_output.txt` — DELETED after use (was one-time transfer)

---

## Znane problemy (remaining):

| Problem | Status | Priority |
|---------|--------|----------|
| bonito — oba IP zblokowane | SHOP_DISABLED, czeka na Play SIM | LOW |
| proshop — IP blocked | SHOP_DISABLED | LOW |
| mediaexpert GraphQL 404 | Fallback goto działa, 4 produkty OK | LOW |
| piwniczaki 50% zeros | Retry łapie dane, strona intermittent | MONITOR |
| wilczek standalone browser | Działa ale spawns own Chrome per scan | MEDIUM (optimize?) |
| CF Bridge transient crashes | Auto-recovery po restarcie, 30min cooldown shops | MONITOR |
| FAST "MOSTLY_EMPTY" shops | Serwery tych sklepów lagują, nie nasz problem | IGNORE |

---

## VPS/Proxy (BEZ ZMIAN):
- VPS: 146.59.45.228, OVH Debian, 4c/8GB
- Phone: 100.127.72.24, SSH 8022, pass 123
- Mobile IP: 37.47.130.139 (Orange PL, static)
- DB: postgresql://pokemonitor:mon2026pg@localhost/pokemonitor

---

## Kluczowe odkrycia tej sesji:

1. **NODRIVER "0 produktow" root cause**: shared page w persistent browser "wysycha" — sesja/cookies expirują, lazy-load nie triggeruje na kolejnych goto(). Fix: przepisać na aiohttp (fresh connection per scan = no state issues).

2. **ENGINE "DEAD" w live_report był FALSE ALARM**: Parser nie łapał `[tcgumisia-proxy] 70 products` (angielski format). Prawdziwy scan log to `[tcgumisia] 70 produktow w 1.5s` — ten BYŁ łapany. Ale report_10h.sh awk tworzył fake shop entries z error message tekstów ("Connect call failed" → fake shop name).

3. **Empik lazy-img**: Niestandardowy atrybut (nie data-src, nie srcset). `<img lazy-img="https://ecsmedia.pl/...">` — jedyne źródło prawdziwego URL.

4. **bonito.pl blokuje WSZYSTKIE IP**: Nie da się obejść bez residential proxy lub nowej SIM. VPS (datacenter) + mobile (Orange CGNAT) oba blocked.

5. **Dragonus/piwniczaki/wilczek nie potrzebowały Chrome**: Proste strony HTML/SPA — Chrome był overkill. aiohttp (dragonus, piwniczaki) i standalone lightweight patchright (wilczek) = 3 mniej procesów Chrome, mniej RAM, szybsze skany.

6. **paste.rs niestabilny**: 500 errors. Alternatywa: push output do repo jako deep_diag_output.txt.
