# TODO — Pokemon Monitor v2

## Ostatnia aktualizacja: 2026-08-20

---

## 🔴 PRIORYTET #1 — Zero-Click Checkout (instant buy via API)

### Sellingo (tcgumisia)
- [ ] Sniff pełny checkout flow: `/ajax/cart/add` + `/ajax/order/create`
- [ ] Zbudować HTTP-only bot (zero Chrome = 100ms vs 5s)
- [ ] Test na koncie testowym
- [ ] Deploy (gdy tcgumisia wróci z pauzy)

### Shoper (kartexpol, strefatcg)
- [ ] Pattern: pre-logged browser session + `page.evaluate("fetch(...)")` for ATC/checkout
- [ ] Wzór: JC Torpedo (już działa — API calls z browser context)
- [ ] Adapter na Shoper flow (login → keep session → ATC via JS fetch → submit)
- [ ] Test na koncie testowym

### Bookland (Magento 2 GraphQL)
- [x] Scraper gotowy
- [ ] Sniff GraphQL mutations: addToCart → setShipping → placeOrder
- [ ] Zbudować autobuy bot
- [ ] Test + deploy

---

## 🟠 PRIORYTET #2 — Nowe Scrapery (lista usera)

### Do sprawdzenia (z listy 2026-08-15, nie zbudowane):
| # | Sklep | Status | Uwagi |
|---|-------|--------|-------|
| 1 | posters.pl | ❌ CF | Wymaga FlareSolverr |
| 2 | kiddin | ❓ | Nie sprawdzony |
| 3 | abondegames.pl | ✅ | Już działa! |
| 4 | archivebyx.com | ✅ | Już działa! |
| 5 | bigcards.pl | ✅ | Już działa! |
| 6 | plastiq.pl | ✅ | Już działa! |
| 7 | eduksiazka.pl | ✅ | Już działa (SLOW, JS) |
| 8 | dystryktzero | ✅ | Już działa (CF, SLOW) |
| 9 | gralnia.pl | ✅ | Już działa (CF, SLOW) |
| 10 | maginarium | ✅ | Już działa (direct aiohttp) |
| 11 | monsteriada | ✅ | Już działa (direct aiohttp) |
| 12 | xjoy.pl | ✅ | Już działa (CF, SLOW) |
| 13 | mepel.pl | ✅ | Już działa (CF, SLOW) |
| 14 | loficards.pl | ✅ | Już działa (FAST) |

### Do zbudowania:
| # | Sklep | Platforma | Uwagi |
|---|-------|-----------|-------|
| 1 | posters.pl | CF | Cloudflare — FlareSolverr |
| 2 | kiddin | ? | Nie sprawdzony |
| 3 | pokeserwis.pl | CF | Pokemon sklep (za Cloudflare) |
| 4 | magicznyrynek.pl | ? | MTG + Pokemon |
| 5 | poksy.eu | ? | Pokemon kolekcjonerskie |
| 6 | mini-figurki.pl | ? | Karty Pokemon TCG |
| 7 | kidozabawki.pl | ? | Zabawki na licencjach |

---

## 🟡 PRIORYTET #3 — Infrastruktura & Optymalizacje

### Bonito / Proshop — IP Reset
- [ ] Druga SIM (Play/T-Mobile prepaid ~5 PLN) = dynamiczny IP
- [ ] Nowy proxy z innym IP → odblokuje bonito + proshop
- [ ] Hardware change (fizycznie włożyć SIM do telefonu)

### MediaExpert GraphQL
- [ ] Debug dlaczego `/api/graphql/product-offer/query/` daje 404
- [ ] Jeśli wróci: poll co 5-10s per product ID = instant stock detection
- [ ] Alternatywa: Synerise search API (publiczny, bez stocku — ograniczony)

### MediaExpert Seller Filtering
- [ ] Filtruj TYLKO produkty sprzedawane przez Media Expert (nie marketplace)
- [ ] Identyfikacja selektora seller info w offer-box
- [ ] Dodać product IDs do WATCH_PIDS w mediaexpert_trigger.py

### Universal Trigger Migration
- [x] trigger_config.json + universal_trigger.py stworzony
- [ ] Wire into detector.py (replace 9 check_* functions with single check_trigger())
- [ ] Test na jednym shopie
- [ ] NIE usuwać starych trigger files dopóki proven na live

---

## 🟢 PRIORYTET #4 — Nice-to-have (long-term)

| # | Feature | Opis |
|---|---------|------|
| 1 | Drop Timing Predictor | ML na event_log — turbo mode PRZED dropem |
| 2 | Sitemap/RSS monitoring | Nowe URL = nowy produkt wkrótce |
| 3 | Redis message queue | Engine → trigger → bot w <10ms |
| 4 | Multi-VPS failover | Backup VPS (overkill na razie) |
| 5 | Payment automation | Przelewy24 API (ryzykowne prawnie) |
| 6 | Auto-selector repair | Heurystyczne porównanie DOM po zmianach layoutu |

---

## ❌ DISABLED / PAUSED:

### tcgumisia autobuy — PAUSED
- Paused od 2026-08-13
- NIE re-enable bez explicit user request
- Scraper + proxy poller DZIAŁAJĄ (70 produktów, 20s poll)
- Bot killed, trigger ma ENABLED=False

### Disabled shopy (nie naprawić bez hardware change):
- **bonito** — IP banned (potrzeba nowej SIM)
- **proshop** — IP blocked (potrzeba nowej SIM)
- **bastacentershop** — kategoria pusta (czekać)
- **mycards, pokesmart, tcglove** — domeny martwe (nigdy)

---

## ✅ ZROBIONE (sesja 2026-08-20 v3):

- [x] Cooldown reset fix (perpetual loop eliminated)
- [x] CF solver 2→4 concurrency
- [x] Empik 85s→36s (sleep reduction + pages 5→3)
- [x] MARK_MISSING_AS_OOS × 14 shopów (2x więcej restocków!)
- [x] Smyk restock detection + coverage (queries + missing=OOS)
- [x] MediaExpert SCAN_DELAY=25s (~3x skanów/h)
- [x] Parallel bots × 3 (kartexpol, strefatcg, jc — asyncio.gather)
- [x] Monsteriada FlareSolverr→aiohttp (108s→5s)
- [x] Maginarium FlareSolverr→aiohttp (114s→5-10s)
- [x] Limango exclude (regały, meble, +38 śmieci usunięte z DB)
- [x] rotate_ip.sh cron usunięty (eliminuje proxy outages co 4h)
- [x] "None" phantom fix w live_report.sh
- [x] CF Audit (gralnia/xjoy/dystryktzero = real CF, am76/eduksiazka = JS SPA)
