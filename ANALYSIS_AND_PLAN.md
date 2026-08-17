# Analiza Systemu + Plan Rozwoju — Pokemon Monitor v2 → v3

## Stan: 2026-08-17 (po sesji stabilizacji)
## Autor: AI Analysis (pełna analiza architektury, kodu, wydajności)

---

## 1. OBECNA ARCHITEKTURA — Co Mamy

```
┌─────────────────────────────────────────────────────────┐
│ main.py (parent) — fork 4 procesów, auto-restart       │
├───────────┬───────────┬────────────┬───────────────────┤
│ FAST      │ SLOW      │ NODRIVER   │ ENGINES           │
│ ~100 shops│ ~20 shops │ ~12 shops  │ 1 engine (tcgum)  │
│ async     │ async     │ subprocess │ async 10s poll    │
│ 5-15s     │ 30-120s   │ 30-120s    │                   │
│ aiohttp   │ FlareSolv │ Chrome     │ HTTP+PoW          │
└─────┬─────┴─────┬─────┴──────┬─────┴────────┬──────────┘
      │           │            │              │
      └───────────┴────────────┴──────────────┘
                        │
                   detector.py
              (RESTOCK/NEW/PRICE_CHANGE)
                        │
              ┌─────────┴─────────┐
              │                   │
         discord_sender.py    *_trigger.py (9 shopów)
         (embeds → webhook)   (→ autobuy bots)
                                  │
                             bot_engine.py
                             (Chrome + API)
```

### Metryki wydajności (obecne):

| Grupa | Shopów | Scan time | Delay | Cykl efektywny | Detekcja |
|-------|--------|-----------|-------|----------------|----------|
| FAST | ~100 | 1-15s | 5-15s | **6-30s** | ✅ Szybka |
| SLOW | ~20 | 30-350s | 30-60s | **60-410s** | ⚠️ Wolna |
| NODRIVER | ~12 | 30-120s | 30-60s | **60-180s** | ⚠️ Wolna |
| ENGINE | 1 | 2-5s | 10s | **12-15s** | ✅ Szybka |

### Co działa dobrze:
1. **Multi-process** — każdy ma swój event loop, zero blokowania
2. **Auto-restart** — crash → restart w 5s
3. **Cross-shop turbo** — restock na tcgumisia → przyspieszenie kartexpol/strefatcg
4. **Discord queue** — fire-and-forget, detekcja nie czeka na webhook
5. **Progressive cooldown** — dead shopy nie marnują zasobów
6. **Proxy failover** — 3 ścieżki + direct

### Co NIE działa / jest wolne:
1. **FlareSolverr** — 30-60s per request, sekwencyjnie w docker, max 512MB
2. **NODRIVER Chrome** — ciężkie, 50-120MB per instancja, wolny startup
3. **1 Discord webhook** — limit 25/min (problem przy 300+ shopach)
4. **Hardcoded triggery** — 9 check_* functions, każdy nowy = edycja detector.py
5. **Brak shared sessions** — każdy FAST shop tworzy nowy TCP connection
6. **Dead shopy** — 18 shopów marnuje zasoby (timeout po timeout)

---

## 2. PORÓWNANIE Z HYDRA PLAN

### Co z HYDRA jest GOTOWE:
| Element | Status | Uwagi |
|---------|--------|-------|
| API engines | ✅ Infrastruktura | engine_runner.py działa, 1 engine aktywny |
| Cross-shop intelligence | ✅ Działa | turbo_mode na CORRELATED_SHOPS |
| Pre-warmed sessions | ✅ session_warmer.py | Cookies per konto, 2h ważność |
| Fingerprint rotation | ✅ bot_engine.py | 5 presetów per konto |
| Human delay | ✅ bot_engine.py | 12-25s między kontami |
| PostgreSQL tracking | ✅ Pełne | event_log, price_history, orders, shop_intel |
| Proxy mesh | ✅ 3 paths | tunnel + tailscale + socks |

### Co z HYDRA jest DO ZROBIENIA:
| Element | Priorytet | Trudność | Impact |
|---------|-----------|----------|--------|
| API engines per shop (Shoper, Sellingo, WooCommerce) | 🔴 HIGH | Średnia | 10x szybsza detekcja |
| Zero-click checkout (API POST) | 🔴 HIGH | Wysoka | 0.1s vs 5s ATC |
| Webhook multiplexing | 🟡 MEDIUM | Niska | Skalowalność 300+ |
| Redis message queue | 🟡 MEDIUM | Średnia | <10ms trigger→bot |
| Drop timing predictor | 🟢 LOW | Wysoka | Proaktywne turbo |
| Auto-selector repair | 🟢 LOW | Bardzo wysoka | Auto-naprawa scraperów |
| Multi-VPS failover | 🟢 LOW | Średnia | Redundancja |

---

## 3. MÓJ PLAN — Co Zrobić Dalej (od najważniejszego)

### FAZA 1: MIGRACJA SLOW → FAST (największy impact, najniższe ryzyko)

**Problem**: 20 shopów używa FlareSolverr (30-60s) bo kiedyś miały Cloudflare.
Wiele z nich MOŻE nie mieć już CF albo mieć słabe CF które da się obejść cookies.

**Plan**:
1. Dla każdego SLOW shopa: `curl -I https://shop.pl` z VPS
   - Jeśli 200 → NIE potrzebuje FS! → przepisz na aiohttp (scan 1-5s zamiast 60s)
   - Jeśli 403 + "cf-ray" → sprawdź czy FlareSolverr response daje cookies → reuse cookies w aiohttp
   - Jeśli true managed challenge → zostaje w SLOW
2. Shopy kandydaci do migracji:
   - `maginarium`, `monsteriada`, `dystryktzero`, `gralnia`, `eduksiazka`
   - `xjoy`, `mepel`, `morigal` — wszystkie nowe, może nie mają CF
   - `sklepkleks`, `strefamtg` — PrestaShop, sprawdzić API
   - `battlestash` — WooCommerce, ma API (już jest!)

**Efekt**: 10-15 shopów z SLOW → FAST = cykl z 60-350s → 5-15s

### FAZA 2: API ENGINES (Hydra core)

**Problem**: HTML scraping to 5-15s per scan. API daje 1-3s.

**Plan** per platforma:
| Platforma | Shopy | Endpoint | Poll interval |
|-----------|-------|----------|---------------|
| **Shoper** | kartexpol, strefatcg | `/webapi/rest/product-stocks` | 5s |
| **WooCommerce** | strefakart, battlestash, tcg-zielona | `/wp-json/wc/store/v1/products` | 10s |
| **Sellingo** | tcgumisia | `/ajax/product/{id}` | 5s (mobile proxy) |
| **Shopify** | pokeloot, skladgier | `/products.json` | 30s (rate limit) |
| **Sky-Shop** | japancollectibles, loficards | `/api/products` | 10s |

**Podejście**: Engine obok starego scrapera. Oba działają. Kto pierwszy wykryje — wygrywa (dedup via shared DB).

### FAZA 3: NODRIVER → LIGHTWEIGHT

**Problem**: 12 shopów w Chrome = 12 × (50-120MB + 30-120s scan).

**Plan per shop**:
| Shop | Obecna metoda | Możliwa alternatywa |
|------|---------------|---------------------|
| empik | nodriver + proxy | FlareSolverr (już tam jest w SLOW!) lub cookies reuse |
| piwniczaki | playwright | Sprawdzić API Sky-Shop |
| wilczek | playwright | Strona prosta, może aiohttp? |
| strefamarzen | playwright | Sprawdzić search API |
| dragonus | playwright | Strona prosta, aiohttp z regex |
| rgfk | playwright | DEAD — syntax error, naprawić lub wyłączyć |
| tantis | patchright (CF) | Cookies reuse? |
| boosterpoint | patchright | Ma WooCommerce API! → engine |
| bonito | patchright + WARP | IP banned, czeka na nową SIM |
| libristo | nodriver | CF hard — zostaje |
| proshop | nodriver | Sprawdzić API |
| battlestash | FlareSolverr | Ma WooCommerce API! → engine |

**Cel**: Zmniejszyć NODRIVER z 12 → 4-5 shopów (tylko te które NAPRAWDĘ wymagają Chrome)

### FAZA 4: WEBHOOK MULTIPLEXING

**Problem**: 1 webhook = 25 msg/min. Przy 300 shopach z aktywnymi dropami to za mało.

**Rozwiązanie**:
```python
# discord_sender.py — round-robin webhooks
WEBHOOKS = [WEBHOOK_1, WEBHOOK_2, WEBHOOK_3]  # 3 webhooks = 75/min
self._webhook_index = 0

async def _send(self, embed):
    url = WEBHOOKS[self._webhook_index % len(WEBHOOKS)]
    self._webhook_index += 1
    ...
```

**Trudność**: Niska. 10 linii kodu + 2 dodatkowe webhooks na Discord.

### FAZA 5: UNIVERSAL TRIGGER (uprościć detector.py)

**Problem**: 9 hardcoded `check_*_trigger()` w detector.py. Każdy nowy trigger = edycja.

**Rozwiązanie** (już istnieje `universal_trigger.py` + `trigger_config.json`):
```python
# detector.py — zamiast 9 check_* functions:
from universal_trigger import check_triggers
check_triggers(event_type, product)  # Czyta z trigger_config.json
```

**Efekt**: Dodanie nowego bota = edycja JSON, zero kodu.

### FAZA 6: SHARED AIOHTTP SESSION

**Problem**: Każdy FAST shop tworzy `aiohttp.ClientSession()` per scan → nowe TCP connections.

**Rozwiązanie**:
```python
# W _async_process — shared session per process
session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=50))
# Przekaż do shop_worker → shop modules
```

**Efekt**: Mniejszy overhead TCP, szybsze scany (connection reuse).

### FAZA 7: ZERO-CLICK CHECKOUT (Hydra v3)

**Cel**: Drop → zamówienie w <2s (bez Chrome, czysty HTTP POST)

| Platforma | Metoda | Latency |
|-----------|--------|---------|
| Sellingo (tcgumisia) | POST `/ajax/cart/add` + `/ajax/order/create` | 0.1-0.5s |
| Shoper (kartexpol, strefatcg) | POST `/webapi/rest/orders` | 0.2-0.5s |
| WooCommerce | POST `/wp-json/wc/store/v1/checkout` | 0.3-0.8s |

**Wymaga**: Reverse-engineering API per platformę. Najwyższy impact ale i ryzyko.

---

## 4. DEAD SHOPY — Co Z Nimi (18 shopów)

| Shop | Problem | Rozwiązanie |
|------|---------|-------------|
| bastacentershop | Timeout 41x | Serwer wolny/dead — sprawdzić ręcznie |
| wargamer | Timeout 40x | Serwer wolny/dead |
| kartexpol | Timeout 40x | Shoper → zbudować API engine! |
| mycards | SSL error | Domena padła — wyłączyć |
| pkmnshop | SSL error | Domena padła — wyłączyć |
| tantis_old | Timeout 34x | DUPLICATE (mamy tantis) — usunąć! |
| mediaexpert | Chrome timeout | nodriver fail → naprawić lub wyłączyć |
| tcglove | SSL error | Domena padła — wyłączyć |
| strefatcg | Timeout 14x | Shoper → zbudować API engine! |
| pegazgry | Timeout 13x | Sprawdzić czy żyje |
| rgfk | Syntax error | Bug w scraperze — naprawić |
| limango | Timeout 9x | Wolny serwer + skomplikowany |
| eduksiazka | Timeout 3x | Nowy scraper — debug na VPS |
| xjoy | Timeout 3x | Nowy scraper — debug na VPS |
| gralnia | Timeout 3x | Nowy scraper — debug na VPS |
| morigal | Timeout 2x | Nowy scraper — debug na VPS |
| dystryktzero | Timeout 2x | Nowy scraper — debug na VPS |
| mepel | Timeout 1x | Nowy scraper — debug na VPS |

**Quick wins**:
- `tantis_old` → usunąć (duplicate)
- `mycards`, `pkmnshop`, `tcglove` → wyłączyć (domeny dead)
- `kartexpol`, `strefatcg` → API engine (Shoper `/webapi/rest/`)
- `rgfk` → naprawić syntax error

---

## 5. ARCHITEKTURA DOCELOWA (300+ shopów)

```
┌──────────────────────────────────────────────────────────────────┐
│                    main.py (supervisor)                            │
├──────────┬──────────┬──────────┬──────────┬─────────────────────┤
│ FAST #1  │ FAST #2  │ SLOW     │ NODRIVER │ ENGINES             │
│ 100 shops│ 100 shops│ 10 shops │ 5 shops  │ 20 engines          │
│ async    │ async    │ FlareSolv│ Chrome   │ API poll 3-10s      │
│ 5-15s    │ 5-15s    │ (only CF)│ (only!)  │ (Shoper,WC,Sell)    │
└────┬─────┴────┬─────┴────┬─────┴────┬─────┴──────────┬──────────┘
     │          │          │          │                │
     └──────────┴──────────┴──────────┴────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │   detector.py     │
                    │ + universal_trigger│
                    └─────────┬─────────┘
                              │
               ┌──────────────┼──────────────┐
               │              │              │
          discord_sender  trigger_engine   event_log (PG)
          (3 webhooks)    (trigger_config)  (analytics)
               │              │
          Discord embeds  ┌───┴────┐
          (75/min max)    │        │
                     Chrome bots  API bots
                     (legacy)     (zero-click)
```

### Różnice vs obecna:
1. **2 procesy FAST** (podział 100+100 shopów) — architektura już to wspiera!
2. **SLOW zredukowany** do 10 shopów (reszta migrowana do FAST)
3. **NODRIVER zredukowany** do 5 shopów (reszta na API/aiohttp)
4. **20 engines** — każda ważna platforma ma API engine
5. **3 webhooks** — rotation, 75 msg/min
6. **Universal trigger** — nowy bot = edycja JSON

### Kluczowa zasada: NIE PSUĆ co działa
- Buduj nowe OBOK starego
- Testuj → plug → stare jako fallback → po tygodniu wyłącz
- FAST shopy NIE RUSZAĆ (100 shopów działa)

---

## 6. JUTRO — Plan Sesji

### Rano (po nocy):
1. `bash infra/night_ip_test.sh check` — czy Orange PL zmienił IP?
2. `bash infra/full_audit.sh` — porównanie z dzisiejszym audytem:
   - Czy timeouty spadły (wolny RAM = szybsze scany)?
   - Czy RAM stabilny (memory_guard działa)?
   - Ile shopów przeszło z struggling → healthy?

### Analiza:
3. Sprawdzić SLOW shopy — curl z VPS, które faktycznie mają CF?
4. Dead shopy — naprawić quick wins (usunąć tantis_old, dead domains)
5. Kartexpol/strefatcg — zacząć budowę Shoper API engine

### Rozwój:
6. Webhook multiplexing (10 min roboty, duży efekt)
7. Pierwszy nowy engine (kartexpol_api.py → `/webapi/rest/product-stocks`)
8. FlareSolverr audit — cookies reuse trick (1 FS request → cookies → aiohttp dalej)

---

## 7. METRYKI SUKCESU (co mierzymy)

| Metryka | Obecna | Cel (1 tydzień) | Cel (1 miesiąc) |
|---------|--------|-----------------|-----------------|
| Shopów total | 171 | 180+ | 250+ |
| Healthy (>70%) | 40 | 100+ | 200+ |
| Dead (0%) | 18 | 5 | 0 |
| Avg detection | 10-60s | 5-15s | 1-5s (API) |
| RAM usage | <2GB | <2GB | <3GB (250 shops) |
| Chrome processes | <60 | <30 | <20 |
| Webhook capacity | 25/min | 75/min | 75/min |
| API engines | 1 | 5 | 15 |
| Uptime | flapping | 99%+ | 99.9% |

---

## 8. ZASADY ROZWOJU (nie łamać!)

1. **FAST shopy NIE RUSZAĆ** — 100 shopów działa, zero powodu do zmian
2. **Buduj OBOK, nie ZAMIAST** — nowy engine obok starego scrapera
3. **Test na VPS przed deploy** — sandbox ≠ VPS (IP, CF, proxy)
4. **Jeden fix na raz** — nie łączyć features z refactorem
5. **Memory guard chroni** — ale nie polegaj na nim, eliminuj źródła leaków
6. **Każdy shop MUSI działać** — nie odpuszczać dead shopów
7. **API-first** — zanim napiszesz scraper HTML, sprawdź czy jest API
8. **Timeout = proporcjonalny** — jeśli shop skanuje 5s, timeout 30s wystarczy
