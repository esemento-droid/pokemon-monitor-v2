# HYDRA v3 — Pokemon Drop Domination System

## Filozofia
- **WSZYSTKIE produkty Pokemon TCG mają RÓWNY priorytet** — brak różnicowania po cenie/popycie
- **Wszystko musi być wykryte ASAP** — kto pierwszy, ten kupuje
- **Build strategy**: buduj NOWE obok STAREGO, zero downtime, zero ryzyka
- **Gradual migration**: nowy komponent testowany → plugowany jako PRIMARY → stary jako FALLBACK → po tygodniu stary wyłączany

---

## Architektura — 7 Filarów

### 1. PREDICTION ENGINE (Silnik Predykcji)
| Komponent | Opis |
|-----------|------|
| Drop timing predictor | Uczy się wzorców dropów per shop (dzień tygodnia, godzina, interwał) |
| Cross-shop correlation | Drop na shop A → turbo mode na wszystkich shopach (już działa w v2!) |
| Sitemap/RSS monitoring | Wykrywanie nowych URL przed publikacją na froncie |
| Price/image anomaly | Cena zmieniona z 0 = imminent drop, nowy obrazek = produkt nadchodzi |

### 2. DEEP EXTRACTION (Głęboka Ekstrakcja)
| Platforma | Endpoint | Metoda |
|-----------|----------|--------|
| **Sellingo** (tcgumisia) | `/ajax/product/{id}` | Direct JSON poll |
| **Shoper** (kartexpol, strefatcg) | `/webapi/rest/product-stocks` | REST API |
| **WooCommerce** (strefakart) | `/wp-json/wc/v3/products` | REST API (już działa!) |
| **PrestaShop** (sklepkleks) | `/api/stock_availables` | REST API |
| **Magento 2** (bookland) | GraphQL `/graphql` | Mutation query |

**Zaawansowane techniki:**
- DOM MutationObserver — trzymaj browser otwarty, wykryj zmianę stocku w 0ms
- Hidden stock detection — hash comparison (zmiana hash = zmiana danych)
- CDN cache bypass — direct origin polling (pomijaj cache frontend)

### 3. EXECUTION SUPREMACY (Supremacja Wykonania)
| Technika | Opis |
|----------|------|
| Pre-warmed sessions | 4 browsery ZAWSZE zalogowane, gotowe do ATC w <1s |
| Zero-click checkout | Direct API POST (Sellingo, Shoper) — bez klikania UI |
| Parallel execution | 4 konta jednocześnie na RÓŻNYCH IP (VPS + mobile + Tailscale) |
| Race condition exploit | ATC w 500ms oknie zanim frontend się zaktualizuje |

### 4. ADAPTATION ENGINE (Silnik Adaptacji)
- **Auto-selector repair** — heurystyczne porównanie DOM, auto-naprawa po zmianach layoutu
- **Strategy evolution** — A/B test strategii, promuj wygrywające
- **Competitive intelligence** — monitoruj konkurencję (czas reakcji na dropy)

### 5. ANTI-DETECTION (Anty-Detekcja)
- **Fingerprint rotation** — osobny fingerprint per konto (bot_engine.py już to robi)
- **Distributed IP** — VPS (OVH) + Mobile (Orange) + Residential (przyszłość)
- **Timing humanizer** — 12-25s delay między akcjami (już w bot_engine.py)
- **Cookie persistence** — zachowaj sesje między restartami

### 6. INFRASTRUCTURE (Infrastruktura Docelowa)
| Komponent | Rola |
|-----------|------|
| **Redis** | Message queue: detection → execution <10ms latency |
| **PostgreSQL + TimescaleDB** | Trend analysis, drop prediction, price history |
| **Multi-node hot standby** | Failover VPS (jeśli primary padnie) |
| **Proxy mesh** | Auto-rotation, health check, fallback chain |

### 7. NUCLEAR OPTIONS (Opcje Ostateczne)
- Human-in-the-loop dla captcha/blocks (Discord notification → user rozwiązuje)
- Email monitoring dla order verification (IMAP polling)
- Payment automation (przyszłość — przelewy24 API)

---

## Build Strategy — Fazy

### Faza 1: API Engines (CZĘŚCIOWO GOTOWA)
- ✅ tcgumisia_api.py (Sellingo) — DISABLED (429 na VPS IP)
- ✅ tcgumisia_proxy_poller.py — ACTIVE (mobile IP, /pre-order, 10s)
- ✅ strefatcg_api.py (Shoper) — DISABLED (user wybrał BS4 scraper)
- ⬜ kartexpol_api.py (Shoper /webapi/) — do zbudowania
- ⬜ strefakart — WooCommerce API (DONE, działa jako scraper)

### Faza 2: Parallel Account Execution
- ⬜ Każde konto na osobnym IP (VPS, mobile, Tailscale exit nodes)
- ⬜ Pre-warmed sessions (login raz, trzymaj cookie)
- ⬜ Bot odpala 4 procesy jednocześnie

### Faza 3: Prediction Engine
- ✅ Cross-shop turbo mode (CORRELATED_SHOPS w detector.py)
- ⬜ Drop timing predictor (ML na event_log z PostgreSQL)
- ⬜ Sitemap monitoring (nowe URL = nowy produkt wkrótce)

### Faza 4: Zero-Click Checkout
- ⬜ Sellingo API checkout (POST /ajax/cart/add + /ajax/order/create)
- ⬜ Shoper API checkout (/webapi/rest/orders)
- ⬜ Eliminacja browser overhead (czysty HTTP = 100ms vs 5s z Chrome)

### Faza 5: Full Automation
- ⬜ Redis queue (engine → trigger → bot w <10ms)
- ⬜ Auto-selector repair
- ⬜ Multi-VPS failover

---

## Obecny Stan v2 → v3 Migration

```
v2 (PRODUKCJA, 140 shopów):
  main.py → shops/*.py (HTML scraping, 5-15s)
  detector.py → *_trigger.py → *_autobuy.py (per-shop boty)

v3 (W BUDOWIE, obok v2):
  engines/engine_runner.py → engines/*.py (API polling, 3-10s)
  → ten sam detector.py (shared)
  → te same triggery (shared)
  
  checkout_engine/ (PLANOWANE):
  → sellingo.py (API checkout)
  → shoper.py (API checkout)
  → universal.py (fallback: Patchright)
```

**Zasada #1**: Stare NIE RUSZAĆ. Nowe budować OBOK. Whichever detects faster — wins.

---

## Kluczowe Metryki (docelowe)

| Metryka | v2 (teraz) | v3 (cel) |
|---------|-----------|----------|
| Detection latency | 5-15s (HTML) | 1-3s (API) |
| ATC latency | 5-10s (browser) | 0.1-0.5s (API POST) |
| Total: drop → order | 15-30s | 2-5s |
| Parallel accounts | 1 (sequential) | 4 (parallel, multi-IP) |
| Success rate | ~25% (1/4 kont) | >90% (parallel + speed) |
