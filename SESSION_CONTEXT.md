# Session Context — Pokemon Monitor v2
## Last updated: 2026-08-09 21:30

---

## W TRAKCIE: TCGumisia Auto-Buy Bot

### Status: CHECKOUT W BUDOWIE — paczkomat dropdown do naprawienia

### Co działa:
- **Login** ✅ — PW `fill()` + `.js-submit-login` click, POST /account/login
- **Clear cart** ✅ — `.c-table-product__delete--desktop` force click, loop until empty
- **ATC** ✅ — `#product-card-add-to-card` click, cena 220 PLN na produkcyjnych kontach
- **InPost radio** ✅ — click label parent of `input[name="shipment"][value="15"]`
- **Wyszukaj button** ✅ — `.inpost_search_point` click
- **Paczkomat search** ✅ — `input[name="easypack-search"]` + `type()` char by char (delay=100ms)
- **Dropdown pojawia się** ✅ — WAW65N widoczny w `.inpost-search__item-list.point`
- **Tab 1 → Tab 2** ✅ — `.js-cart-next` force=True

### Co NIE działa (do naprawienia):
1. **Kliknięcie dropdown itemu WAW65N** — bot nie klika `.inpost-search__item-list.point`
2. **Blik radio** — `input[name="payment"][value="25"]` (hidden dopóki InPost nie wybrane, ale force=True powinno)
3. **Tab 2 → Tab 3** — nie przechodzi (pewnie regulamin `input[name="rules"]` nie zaznaczony bo widgetInPost blokuje)
4. **Zamawiam i płacę** — nie klika bo nie jest na Tab 3

### Konto testowe `t11008543@gmail.com`:
- **ZFLAGOWANE** przez Sellingo — produkty dodane przez bota mają cenę 0 PLN
- Na produkcyjnych kontach (esemento) cena jest prawidłowa (220 PLN) ✅
- Hasło: `mt!cSsphud4Zhnz`
- Paczkomat testowy: **WAW65N** (nie PAD04M!)

### Kluczowe selektory Sellingo (tcgumisia.pl):
```
LOGIN:
  Modal open: button[data-aside-target="modal-aside-entry-form"]
  Form: .js-login-form
  Email: .js-login-form input[type="email"]
  Password: .js-login-form input[type="password"]
  Submit: .js-submit-login
  Cookie accept: .js-accept-cookie-alert-1

CART:
  Delete item: .c-table-product__delete--desktop (force=True)
  Empty text: "koszyk jest pusty"

ATC:
  Button: #product-card-add-to-card
  Cart value check: .js-cart-value

CHECKOUT TAB 1 (Koszyk):
  InPost radio: input[name="shipment"][value="15"] — CLICK PARENT LABEL
  Odbiór osobisty: input[name="shipment"][value="7"] (domyślny)
  Wyszukaj: .inpost_search_point (DIV not button!)
  Search input: input[name="easypack-search"] — use type() not fill()!
  Dropdown item: .inpost-search__item-list.point — KLIKNĄĆ TU!
  Blik radio: input[name="payment"][value="25"] (hidden initially, force=True)
  Przelew radio: input[name="payment"][value="4"] (domyślny)
  Dalej: .js-cart-next (force=True, widget blokuje pointer)

CHECKOUT TAB 2 (Dane):
  Regulamin: input[name="rules"] (force=True)
  Przejdź dalej: .js-cart-next (force=True)

CHECKOUT TAB 3 (Płatność):
  Zamawiam: button/a containing "zamawiam"
```

### Fingerprint fix (w kodzie):
- `viewport: 1920x1080`
- `locale: pl-PL`
- `add_init_script`: platform=Win32, languages pl-PL — ALE NIE DZIAŁA (Patchright ignoruje)
- Mimo to bot nie jest wykrywany — cena OK na produkcyjnych kontach

### Pliki:
- `/opt/pokemon-monitor-v2/tcgumisia_autobuy.py` — główny bot
- `/opt/pokemon-monitor-v2/tcgumisia_trigger.py` — trigger (30th keywords, batch mode)
- `/opt/pokemon-monitor-v2/test_full_flow.py` — test script (prawdziwe zamówienie)
- Debug files (do usunięcia): debug_atc.py, debug_login.py, debug_cart.py, debug_clearcart.py, debug_checkout.py, debug_fingerprint.py, debug_esemento_cart.py

### Następne kroki:
1. Naprawić klik na dropdown WAW65N (`.inpost-search__item-list.point`)
2. Po wybraniu paczkomatu zamknąć widget (klik "Wybierz" lub "✕")
3. Wybrać Blik (`payment=25`)
4. Kliknąć Dalej (Tab 1→2)
5. Zaznaczyć regulamin (`rules`)
6. Kliknąć Przejdź dalej (Tab 2→3)
7. Kliknąć Zamawiam (Tab 3)
8. Sprawdzić zamówienie na mailu — czy InPost + Blik + prawidłowa cena
9. Przenieść fixy z test_full_flow.py do tcgumisia_autobuy.py
10. Podpiąć trigger w detector.py
11. Usunąć debug files
12. Push + restart

---

## AKTYWNE BOTY AUTO-BUY (uzbrojone, gotowe na drop):

### 1. Kartexpol (NOWY — 2026-08-08)
- **Plik:** `/opt/pokemon-monitor-v2/kartexpol_autobuy.py`
- **Trigger:** `/opt/pokemon-monitor-v2/kartexpol_trigger.py`
- **Metoda:** Patchright headless=False + mobile proxy (`127.0.0.1:8888`)
- **Flow:** Login → ATC → Checkout single-page (paczkomat + BLIK + zgody) → "Zamawiam i płacę" → Autopay redirect
- **Konta:** 4 produkcyjne + 1 test (t11008543)
- **Status:** ✅ DZIAŁA

### 2. Strefa-TCG
- **Status:** ✅ DZIAŁA

### 3. Empik
- **Status:** ✅ DZIAŁA

### 4. Tantis
- **Status:** ✅ DZIAŁA

### 5. Smyk
- **Status:** ✅ DZIAŁA

### 6. JapanCollectibles (30th batch)
- **Status:** ✅ DZIAŁA

---

## Mobile Proxy (aktywne):
- **Lokalne:** `127.0.0.1:8888` (tinyproxy na VPS)
- **Używają:** empik, kartexpol, tcgumisia (w budowie), scrapery

---

## Komendy VPS:
```bash
# Git pull + restart:
cd /opt/pokemon-monitor-v2 && sudo git fetch origin && sudo git reset --hard origin/main && sudo systemctl restart pokemon-monitor-v2

# Test tcgumisia:
DISPLAY=:99 timeout 300 venv/bin/python3 test_full_flow.py 2>&1 | curl -s -d @- https://paste.rs/

# Full report:
bash <(curl -s https://paste.rs/T4qdZ) 2>&1 | curl -s -d @- https://paste.rs/
```
