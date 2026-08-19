# Session Context — 2026-08-19 (mediaexpert + tcgumisia + price_compare)

## ZASTĘPUJE: SESSION_CONTEXT_2026-08-18_v5.md

---

## ⚠️ OBOWIĄZKOWE NA START KAŻDEJ NOWEJ SESJI

```
cd /opt/pokemon-monitor-v2 && bash infra/live_report.sh && curl -sF 'file=@/tmp/live_report.txt' https://paste.rs
```

---

## Co zrobiono w tej sesji:

### 1. mediaexpert.pl — PRZEBUDOWANY (SICK → OK)

**Problem**: Patchright stealth scraper crashował (TargetClosedError), 70-77s avg, 14-16 timeoutów/h, SICK.

**Rozwiązanie**: HYBRID architektura — full goto + GraphQL polling (w trakcie rozwoju).

**Stan OBECNY (production, działa):**
- mediaexpert wrócił do NODRIVER_SHOPS (był usunięty!)
- SCAN_TIMEOUT = 150s
- Avg scan: **12-18s** (vs 70-77s wcześniej)
- Timeouty: **0** (vs 14-16)
- Status: **OK**
- Skanuje co 60-120s (NODRIVER delay)
- Full goto na każdy scan (GraphQL 404 — do naprawy)

**Co odkryto (API sniff):**
- `prod-api.mediaexpert.pl/api` — backend API (wymaga CF)
- `api.synerise.com/search/v2/indices/...` — search engine (publiczny, bez stocku)
- `/api/graphql/product-offer/query/{ts}?query=...` — GraphQL z ceną + stock per product ID
- GraphQL działa TYLKO z przeglądarki na mediaexpert.pl (same-origin + CF cookies)
- Problem: `/api/*` zwraca 404 z mobile proxy — prawdopodobnie WAF block lub routing change
- Sniff z rana (07:00) dawał 200, wieczorem (22:00) daje 404 — niestabilny endpoint

**TODO mediaexpert (nienajważniejszy):**
- [ ] Debug dlaczego GraphQL daje 404 (WAF? routing change? IP block?)
- [ ] Jeśli GraphQL wróci — polling co 10-20s = instant detection
- [ ] Alternatywa: skrócić NODRIVER delay do 20-30s (50+ skanów/h vs obecne 14/h)
- [ ] Rozważyć: Synerise search API (publiczny) — może da się wyciągnąć stock info

### 2. tcgumisia — PROXY POLLER NAPRAWIONY (przegapiony restock ETB 30th)

**Problem**: Restock ETB 30th przeszedł niezauważony.

**Root cause (2 bugi):**
1. Proxy poller pollował TYLKO `/pre-order` — ale ETB 30th jest na **`/pokemon`**!
2. Availability parsing zepsuty: "Dodano do koszyka" (toast text) na WSZYSTKICH produktach → logic flipował OOS na available → nigdy nie wykrywał restocku

**Fix:**
- Proxy poller teraz polluje **OBIE strony** (`/pokemon` + `/pre-order`), dedup po slug
- Availability: usunięty fałszywy "koszyk" check — tylko `"niedostępn"` = OOS
- Podwójne pokrycie: VPS scraper (co ~19s) + proxy poller (co ~20s)
- Brak kolizji: kto pierwszy wykryje restock → pisze do DB → drugi widzi updated state

**Stan**: ✅ Działa. 70 produktów (pokemon+pre-order), prawidłowa dostępność.
- Uwaga: proxy poller miał chwilowy DEAD (proxy hiccup) — po restarcie wraca sam.

### 3. price_compare (limango LEGO) — FUZZY MATCHING NAPRAWIONY

**Problem**: Porównanie cen matchowało po 1 słowie (np. "Parrot" → 3 losowe polybagi zamiast set 31136).

**Fix:**
- `match_set_number()` threshold: `score >= 1, coverage >= 30%` → **`score >= 2, coverage >= 40%`**
- Wymaga min 2 wspólne słowa — eliminuje false-positive po "creator", "city", "parrot"
- limango regex: `\b(\d{5})\b` → **`\b(\d{4,6})\b`** (łapie 4-6 cyfrowe set numbers)

### 4. Chrome — STABILNY

- 40-42 procesów (plateau)
- Trend: stable / shrinking
- 0 heals/h
- +2-3 to noise z cf_solver context recovery (nie leak)

---

## Stan systemu po sesji (22:00, 2026-08-19):

| Metryka | Wartość |
|---------|---------|
| Scans/h | 12,317 |
| Error rate | 0.4% |
| Timeout rate | 0.5% |
| SCANNING | 137-139 |
| SICK+DEAD | 1 (None=parser artifact) |
| Chrome | 40-42 (stable) |
| Load | 5-6 |
| RAM free | 1.3-1.5 GB |
| mediaexpert | OK (14 scans/h, 18s avg, 0 tout) |
| tcgumisia | OK (99-103 scans/h, 0 errors) |
| tcgumisia-proxy | ENGINE: polling /pokemon + /pre-order |

---

## Architektura (po tej sesji):

```
main.py (supervisor — 5 processes)
├── FAST-1 (~57 shopów) — asyncio/aiohttp
├── FAST-2 (~57 shopów) — asyncio/aiohttp
├── SLOW (~18-20 shopów) — CF Bridge :8191 → cf_solver (CONTEXT POOL)
├── NODRIVER (11 shopów) — browser_manager (SHARED CONTEXT per browser)
│   ├── Stealth: empik, mediaexpert, libristo, proshop, boosterpoint, tantis, bonito
│   ├── Standard: wilczek, dragonus, piwniczaki, rgfk, strefamarzen
│   ├── mediaexpert: HYBRID (full goto 12-18s, GraphQL TODO)
│   ├── SCAN_TIMEOUT: stealth=120s (mediaexpert=150s, proshop=180s), standard=90s (bonito=150s)
│   ├── Heal: reload → max 3 heals → 30min cooldown
│   └── 0 heals/h
└── ENGINES (1: tcgumisia_proxy_poller → /pokemon + /pre-order, 20s interval)
```

---

## Triggery (BEZ ZMIAN):
kartexpol, tantis, empik, smyk, japancollectibles, jc_30th, mediaexpert, strefatcg (max 1501 PLN), tcgumisia (ONLY ETB 30th < 410 PLN)

---

## Pliki zmienione w tej sesji:
- shops/mediaexpert.py (HYBRID architecture, SCAN_TIMEOUT 150, goto 30s, reduced sleeps)
- main.py (mediaexpert added back to NODRIVER_SHOPS)
- engines/tcgumisia_proxy_poller.py (poll /pokemon + /pre-order, fix availability)
- price_compare.py (fuzzy threshold score>=2, coverage>=40%)
- shops/limango.py (set number regex 4-6 digits)
- infra/debug_tcgumisia.py (NEW — diagnostic)
- infra/sniff_mediaexpert.py (NEW — API discovery)
- infra/sniff_mediaexpert2.py (NEW — prod-api probing)
- infra/test_mediaexpert_api.py (NEW — Synerise + GraphQL test)
- infra/test_me_graphql.py (NEW — cf_solver + GraphQL)
- infra/test_me_parse.py (NEW — HTML parse debug)
- infra/test_me_gql_fix.py (NEW — URL format debug)
- infra/test_me_gql2.py (NEW — same-origin fetch test)
- infra/test_gql_minimal.py (NEW — minimal GraphQL variants)

---

## Znane problemy (remaining):

| Problem | Status | Priority |
|---------|--------|----------|
| mediaexpert GraphQL 404 | Endpoint blocked/changed, fallback to full goto works | LOW |
| mediaexpert delay 60-120s | Skrócić do 20-30s? (więcej skanów/h) | MEDIUM |
| pokeverse | Was DEAD, now 89 scans/h → self-healed | DONE |
| tcgumisia-proxy DEAD | Proxy hiccup → auto-recovers after restart | MONITOR |
| Chrome +2 | Noise from cf_solver, plateau 40-42 | OK |

---

## VPS/Proxy (BEZ ZMIAN):
- VPS: 146.59.45.228, OVH Debian, 4c/8GB
- Phone: 100.127.72.24, SSH 8022, pass 123
- Mobile IP: 37.47.130.139 (Orange PL)
- DB: postgresql://pokemonitor:mon2026pg@localhost/pokemonitor

---

## Ważne odkrycia (mediaexpert API):
- `prod-api.mediaexpert.pl/api` — ich backend (clientId w spark-state)
- GraphQL: `/api/graphql/product-offer/query/{timestamp}?query=...`
  - Returns: price_gross, promo_price_gross, ozg.status (availability), pickupDate
  - Wymaga: same-origin fetch z page na mediaexpert.pl + CF cookies
  - Status: 404 z mobile proxy wieczorem (WAF/rate limit?)
- Synerise: `api.synerise.com/search/v2/indices/{index}/query?query=...&token=AC3815B3...`
  - Publiczny, bez auth, 50 wyników
  - NIE ma availability/stock info
  - Token stały: AC3815B3-B512-1F8F-F6CB-3754D3D58BF9
- SKU IDs w meta tag `product:skusPage` (na search page, nie na category SPA)
- prodsklimat array w `<script>` (product IDs for klimat recommendations)
