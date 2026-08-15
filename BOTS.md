# Boty Autobuy — Pokemon Monitor v2

## Konta

### Konto testowe (do testów botów):
| Pole | Wartość |
|------|---------|
| Email | t11008543@gmail.com |
| Hasło | mt!cSsphud4Zhnz |
| Imię | Marian Wasilewski |
| Adres | Konduktorska 14, 00-775 Warszawa |
| Telefon | 672245321 |

**ZASADY:**
- `--test` flag = użyj testowego konta ale zamówienie jest **REALNE** (nie dry-run!)
- Konto tylko do testów — NIGDY na produkcji
- Bot przechodzi CAŁY flow (login, ATC, checkout, adres) i klika finalne potwierdzenie
- Test = pełne zamówienie na testowym koncie (weryfikacja end-to-end)

### Konta produkcyjne:
| Email | Sklepy |
|-------|--------|
| esemento@gmail.com | kartexpol, strefatcg, japancollectibles, tantis, smyk, empik, mediaexpert |
| blackmat36@gmail.com | tcgumisia, kartexpol, strefatcg, japancollectibles, tantis |
| tjbtaniojuzbylo@gmail.com | tcgumisia, kartexpol, strefatcg, japancollectibles |
| y24015411@gmail.com | tcgumisia, kartexpol, strefatcg, japancollectibles |

---

## Aktywne Boty

### kartexpol_autobuy.py
| Parametr | Wartość |
|----------|---------|
| Metoda | Patchright + mobile proxy |
| Status | ✅ Active |
| Trigger | kartexpol_trigger.py |
| Events | NEW_PRODUCT, RESTOCK |
| Rules | `30th|30 celebration|30-lecie` max 500 PLN, qty 1-2 |
| Accounts | 4 (esemento, blackmat36, tjb, y24015411) |
| Batch mode | Yes |

### strefatcg_autobuy.py
| Parametr | Wartość |
|----------|---------|
| Metoda | Patchright + mobile proxy |
| Status | ✅ Active (trigger max_price 1580 PLN) |
| Trigger | strefatcg_trigger.py |
| Events | NEW_PRODUCT, RESTOCK |
| Rules | `30th|30 celebration|30-lecie` max 500 PLN, qty 1-2 |
| Accounts | 4 (esemento, blackmat36, tjb, y24015411) |
| Batch mode | Yes |
| Platform | Shoper |

**WAŻNE:** 
- Trigger zakomentowany w detector.py od 2026-08-12 22:49
- NIE odblokować bez wyraźnej prośby usera
- Bot odpalał się na "30th" za 1750 PLN — user NIE chce auto-kupowania na strefatcg bez kontroli
- max_price ustawione na 1580 PLN (user chce 30th zestawy poniżej 1580)

### japancollectibles_autobuy.py
| Parametr | Wartość |
|----------|---------|
| Metoda | Patchright + mobile proxy |
| Status | ✅ Active |
| Trigger | japancollectibles_trigger.py + japancollectibles_30th_trigger.py |
| Events | NEW_PRODUCT, RESTOCK |
| Rules | `30th|30 celebration` max 600-800 PLN, qty 1-3 |
| Accounts | 4 (esemento, blackmat36, tjb, y24015411) |
| Batch mode | Yes |

### smyk_autobuy.py
| Parametr | Wartość |
|----------|---------|
| Metoda | Playwright + mobile proxy |
| Status | ✅ Active |
| Trigger | smyk_trigger.py (check_smyk_autobuy) |
| Events | NEW_PRODUCT, RESTOCK, PRICE_CHANGE |
| Rules | `pokemon|pikachu` max 400 PLN, qty 1 |
| Accounts | 1 (esemento) |
| Batch mode | No |

### tantis_autobuy.py
| Parametr | Wartość |
|----------|---------|
| Metoda | API + Patchright + mobile proxy |
| Status | ✅ Active |
| Trigger | tantis_trigger.py |
| Events | NEW_PRODUCT, RESTOCK |
| Rules | `30th|30 celebration|30-lecie` max 500 PLN, qty 1-2 |
| Accounts | 2 (esemento, blackmat36) |
| Batch mode | Yes |

### empik_autobuy.py
| Parametr | Wartość |
|----------|---------|
| Metoda | nodriver + mobile proxy |
| Status | ✅ Active |
| Trigger | empik_trigger.py |
| Events | NEW_PRODUCT, RESTOCK |
| Rules | `pokemon|pikachu|tcg` max 500 PLN, qty 1-2 |
| Accounts | 1 (esemento) |
| Batch mode | No |
| WAŻNE | Bot trigger filters by stock='empik' only (marketplace products tracked but NOT bought) |

### tcgumisia_autobuy.py
| Parametr | Wartość |
|----------|---------|
| Metoda | Patchright + mobile proxy |
| Status | ⏸️ PAUSED (od 2026-08-13) |
| Trigger | tcgumisia_trigger.py |
| Accounts | 3 (blackmat36, tjb, y24015411) |
| Batch mode | Yes |
| Platform | Sellingo |

**Pauza:**
- main.py skip + engine registry empty + trigger ENABLED=False + autobuy killed
- Branch ops/disable-tcgumisia deployed
- Backup: /opt/pokemon-monitor-v2/data/tcgumisia-disable-backup-20260813175019
- NIE re-enable bez explicit user request

**Test order #7616** (2026-08-11): Mega Moonlit Tin 3szt + Mega Darkrai 2szt = 682 PLN
- Bug found: clear_cart() only used .c-table-product__delete--desktop (nie matchowało)
- Fix: 10 fallback selectors

### mediaexpert_autobuy.py
| Parametr | Wartość |
|----------|---------|
| Metoda | nodriver + mobile proxy |
| Status | ✅ Written but UNTESTED on live |
| Trigger | mediaexpert_trigger.py (WATCH_PIDS empty!) |
| Events | NEW_PRODUCT, RESTOCK |
| Rules | `pokemon|tcg` max 500 PLN, qty 1 |
| Accounts | 1 (esemento) |
| TODO | Needs product IDs added after seller filtering confirmed |

---

## Bot Engine (bot_engine.py)

Wspólny moduł dla botów:
- Per-account browser (osobny proces)
- Fingerprint rotation per konto
- Proxy routing (mobile IP)
- Timing humanizer (12-25s delay między akcjami)
- Cookie persistence (data/cookies/)

---

## Trigger System

### Obecny stan (detector.py):
9 osobnych triggerów wywoływanych per-event:
```python
check_smyk_autobuy(shop_name, event, product)
check_kartexpol_trigger(event, product)
check_tantis_trigger(event, product)
check_empik_trigger(event, product)
check_strefatcg_trigger(event, product)  # ← zakomentowany!
check_japancollectibles_trigger(event, product)
check_jc_30th_trigger(event, product)
check_tcgumisia_trigger(event, product)
check_mediaexpert_trigger(event, product)
```

Plus flush functions (batch mode):
```python
flush_kartexpol_batch()
flush_tantis_batch()
flush_jc_30th_batch()
flush_tcgumisia_batch()
flush_strefatcg_batch()
```

### Universal Trigger (trigger_config.json + universal_trigger.py):
- JSON config per-shop: match keywords, exclude, qty_min/max, max_price, accounts, bot path
- Hot-reloadable (60s)
- **NOT YET WIRED** into detector.py (stare 9 triggerów nadal aktywne)
- Migration pending: replace 9 check_* calls with single check_trigger() + flush_all_batches()
- NIE usuwać starych trigger files dopóki universal nie jest proven na live

---

## Boosterpoint Bot (boosterpoint_bot.py + boosterpoint_config.json)

Osobny bot (nie w trigger system):
- Scraper + autobuy w jednym
- Config w boosterpoint_config.json

---

## Kluczowe Zasady Botów

1. **`--test` = REALNE zamówienie** na koncie testowym (nie dry-run)
2. **NIGDY nie zmieniaj działającego bota** — nawet jeśli widzisz "lepszy" sposób
3. **Per-account browser** — osobny fingerprint, proxy, cookies per konto
4. **Humanizer** — 12-25s delay (nie 2s jak maszyna)
5. **Dedup** — sprawdź czy bot nie został już odpalony na ten produkt w ostatnich 5 min
6. **max_price** — ZAWSZE sprawdzaj przed trigger (strefatcg: 1580 PLN)
7. **Parallel ≠ sequential** — docelowo 4 konta na 4 IP jednocześnie (teraz: sekwencyjnie)

---

## Platformy e-commerce (checkout flow)

| Platforma | Sklepy | Bot method | API checkout? |
|-----------|--------|------------|---------------|
| Sellingo | tcgumisia | Patchright | ⬜ Possible (/ajax/cart/add + /ajax/order/create) |
| Shoper | kartexpol, strefatcg | Patchright | ⬜ Possible (/webapi/rest/orders) |
| WooCommerce | strefakart | — | ⬜ Possible (/wp-json/wc/store/checkout) |
| Magento 2 | bookland | — | ⬜ Possible (GraphQL mutation) |
| Custom | japancollectibles | Patchright (Angular) | ❌ |
| Custom | empik | nodriver | ❌ |
| Custom | smyk | Playwright | ❌ |
| Custom | mediaexpert | nodriver | ❌ |
| Custom | tantis | API + Patchright | Partially (ATC via API) |
