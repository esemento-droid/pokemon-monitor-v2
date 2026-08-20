# Boty Autobuy — Architektura & Zasady Budowania

## 🎯 CEL: Zamówienie w <5s od restocku

---

## 📐 Architektura — 3 Poziomy Szybkości

### Poziom 1: TORPEDA (~2-4s) — najszybszy
**Kiedy:** Znasz target product z góry (np. Pakiet 30th). Czekasz na restock.

```
Daemon (zawsze działa):
├── Browser z pre-zalogowanymi kontami
├── Checkout pre-staged (/order z BLIK + delivery + checkboxes)
├── Self-poll target product co 5s (ATC attempt = stock check)
└── Na restock: API cart swap + klik submit = 2-3s
```

**Wymagania:**
- Stały target product (znany product_id)
- Platforma z wewnętrznym API (Sky-Shop, WooCommerce, Shoper)
- Browser do submit (jeśli CF/csrf wymaga render)

### Poziom 2: SZYBKI BOT (~10-15s) — dla nowych produktów
**Kiedy:** Nie znasz produktu z góry. Scraper wykrywa nowy/restock → bot kupuje.

```
Trigger (scraper/detector):
├── Wykryty restock/nowy produkt
├── Daemon z pre-zalogowanymi kontami (browser already running)
└── ATC + checkout = 10-15s (bo musi przejść pełny flow)
```

### Poziom 3: COLD BOT (~30-60s) — legacy/fallback
**Kiedy:** Brak daemon, brak pre-login. Stary bot.

```
Trigger → start browser → login → ATC → checkout → submit
(każdy krok od zera = wolno)
```

---

## 🔍 PROCES BUDOWANIA NOWEGO BOTA (krok po kroku)

### 1. SNIFF FIRST (KRYTYCZNE!)

**NIGDY nie pisz bota bez sniffa.** Zawsze najpierw:

```python
# infra/sniff_{shop}_checkout.py
# Playwright z network recording → przejdź cały flow → zapisz WSZYSTKIE requesty
page.on("request", capture)
page.on("response", capture)
# Login → ATC → Cart → Checkout → (NIE klikaj submit) → dump state
```

**Co wyciągnąć ze sniffa:**
- Endpoint login (POST params, csrf)
- Endpoint ATC (API? klik? POST?)
- Jak wygląda checkout (form action, hidden inputs, radio names/values)
- Czy jest CF na checkout (403 = tak)
- Jakie cookies są wymagane
- Shipment/payment IDs (stałe per-shop)

### 2. API DISCOVERY

**Szukaj wewnętrznych API — priorytet:**

| Platforma | API Pattern | ATC Endpoint |
|-----------|-------------|--------------|
| **Sky-Shop** | `/proxy_public_api?endpoint=/sky2/api-public/carts/{id}/items` | POST JSON `{productId, quantity, parameters}` |
| **WooCommerce** | `/wp-json/wc/store/v1/cart/add-item` | POST `{id, quantity}` |
| **Shoper** | `/webapi/rest/carts` | POST JSON |
| **Sellingo** | `/ajax/cart/add` | POST form |
| **Shopify** | `/cart/add.js` | POST JSON `{items: [{id, quantity}]}` |
| **PrestaShop** | `/cart?add=1&id_product=X` | GET |

**Jak znaleźć:**
1. Network tab sniff (najlepsze)
2. `view-source:` → szukaj `/api`, `/ajax`, `/proxy`, `fetch(`, `$http`
3. Sitemap.xml → jeśli jest `/wp-json/` = WooCommerce
4. Headers response → `X-Powered-By`, `Server` → platforma
5. HTML meta: `<meta name="generator" content="Sky-Shop">`

### 3. STOCK CHECK — jak najszybciej

**Najszybsze metody (od najlepszej):**

| Metoda | Speed | Opis |
|--------|-------|------|
| ATC attempt | 0.2s | POST ATC → 200=available, 400=OOS. Stock check = kupno w jednym! |
| Cart API | 0.2s | GET `/api/cart` (niektóre zwracają stock info) |
| Product API | 0.3s | GET `/api/products/{id}` → `is_in_stock` |
| Product page fetch | 0.5s | GET page → parse "Do koszyka" vs "niedostępn" |
| Browser check | 3-5s | Playwright goto → parse (najwolniejsze) |

**ATC attempt jest NAJLEPSZY** bo:
- Jeśli available → produkt JUŻ w koszyku (0 dodatkowego czasu na ATC!)
- Jeśli OOS → response mówi wprost (`ERROR_PRODUCT_OUT_OF_STOCK`)
- 1 request = stock check + ATC w jednym

### 4. CHECKOUT — PRE-STAGED PATTERN

**Zasada:** Wszystko co możesz zrobić PRZED restockiem — zrób wcześniej.

```
PRE-STAGE (idle, co 30 min):
  ✅ Login
  ✅ Stage product w koszyku (tani, dostępny)
  ✅ Przejdź do /order
  ✅ Wybierz payment (BLIK)
  ✅ Wybierz delivery (Kurier)
  ✅ Zaznacz checkboxes
  ✅ csrf token wyrenderowany
  ✅ "Zamawiam" button ready

NA TRIGGER (hot path):
  → API cart swap (clear + ATC target) = 0.5-1s
  → Klik submit = 1s
  DONE
```

### 5. SESSION MANAGEMENT

**Sesja NIE MOŻE wygasnąć.** Pattern:
- **Heartbeat co 5 min:** lekki fetch do API (keep session alive)
- **Re-stage co 30 min:** pełny reload /order (fresh csrf)
- **Re-login jeśli 401/403:** auto-detect expired session

**Stage product fallback:** Lista 3-5 tanich, zawsze dostępnych produktów. Jeśli pierwszy OOS → następny.

### 6. PARALLEL EXECUTION

**Wszystkie konta JEDNOCZEŚNIE:**
```python
tasks = [fire_one(email, product_id) for email in accounts]
results = await asyncio.gather(*tasks)
```

NIE sekwencyjnie! `asyncio.gather` = 4 konta w tym samym czasie.

### 7. SAFETY

| Zasada | Implementacja |
|--------|---------------|
| 1x per konto per product | `completed.json` check before fire |
| Nie zamów stage product | Cart swap (clear ALL → ATC target) before submit |
| Rate limit protection | Poll interval 5s + random jitter |
| Auto-recovery | systemd RestartSec=30 |
| Session expiry | Heartbeat + re-stage |
| Proxy failure | Log + retry after restart |

---

## 🏗️ TEMPLATE: Nowy Torpedo Bot

```
1. Sniff checkout (infra/sniff_{shop}_checkout.py)
2. Identify:
   - Login endpoint + params
   - ATC API endpoint + params
   - Payment IDs (BLIK, przelew, etc.)
   - Shipment IDs (kurier, paczkomat, etc.)
   - Checkout submit endpoint + required fields
   - Czy CF blokuje submit? (403 = potrzebny browser)
3. Decide architecture:
   - Pure HTTP possible? (no CF on submit) → fastest (~1s)
   - CF on submit? → hybrid (HTTP ATC + browser submit) (~3s)
   - Full SPA? → browser with pre-stage (~5s)
4. Build daemon:
   - Login + stage on start
   - Self-poll target product
   - Fire on restock
   - Maintenance (heartbeat + re-stage)
5. Deploy as systemd service
6. Add to live_report.sh monitoring
```

---

## 📊 Porównanie Platform

| Platforma | Pure HTTP ATC | Pure HTTP Submit | CF na checkout | Czas realny |
|-----------|:---:|:---:|:---:|---|
| Sky-Shop (JC) | ✅ | ❌ (CF 403) | ✅ | ~3s (hybrid) |
| Sellingo (tcgumisia) | ✅ `/ajax/cart/add` | ✅ `/ajax/order/create` | ❌ | ~1s (pure HTTP) |
| Shoper (kartexpol) | ✅ `/webapi/rest/` | ✅ | ❌ | ~1s (pure HTTP) |
| WooCommerce | ✅ `/wp-json/` | ⚠️ (zależy) | ❌ usually | ~2s |

**Sellingo i Shoper = najłatwiejsze do pure HTTP torpedo (<1s)!**

---

## 🔧 Narzędzia

| Tool | Użycie |
|------|--------|
| `infra/sniff_{shop}_checkout.py` | Network recording podczas checkout |
| `infra/test_oos_atc.py` | Test ATC na OOS produkt |
| `infra/test_prestaged_submit.py` | Test pre-staged submit bez reload |
| Playwright `page.on("request/response")` | Live network capture |
| `page.evaluate("fetch(...)")` | API call z browser session (same cookies!) |
| `document.cookie.match(/key=([^;]+)/)` | Extract cookie w browser JS |

---

## ⚡ GOLDEN RULES

1. **SNIFF FIRST** — nigdy nie pisz bota bez zobaczenia network traffic
2. **API > BROWSER** — jeśli jest API, użyj go (10x szybciej)
3. **PRE-STAGE** — wszystko co możesz zrobić wcześniej, zrób wcześniej
4. **ATC = STOCK CHECK** — próba dodania do koszyka = sprawdzenie dostępności
5. **SELF-POLL > SCRAPER TRIGGER** — bot sam monitoruje = 0s delay
6. **PARALLEL** — nigdy sekwencyjnie, zawsze `asyncio.gather`
7. **1 REQUEST = 1 ACTION** — nie rób 5 requestów gdzie wystarczy 1
8. **KEEP SESSION ALIVE** — heartbeat, nie pozwól wygasnąć
9. **FALLBACK** — stage product OOS? Miej listę alternatyw
10. **TEST NA OOS** — przed deploy sprawdź co API zwraca na niedostępny produkt
