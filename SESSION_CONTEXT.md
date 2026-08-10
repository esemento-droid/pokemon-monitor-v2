# Session Context — Pokemon Monitor v2
## Last updated: 2026-08-09 21:30

---

## W TRAKCIE: TCGumisia Auto-Buy Bot

### Status: ✅ GOTOWY — podpięty do monitora, czeka na trigger

### Co działa:
- **Login** ✅ — PW `fill()` + `.js-submit-login` click, POST /account/login
- **Clear cart** ✅ — `.c-table-product__delete--desktop` force click, loop until empty
- **ATC** ✅ — `#product-card-add-to-card` click
- **InPost radio** ✅ — click label parent of `input[name="shipment"][value="15"]`
- **Wyszukaj button** ✅ — `.inpost_search_point` click (force=True)
- **Paczkomat search** ✅ — `input[name="easypack-search"]` + `type()` char by char (delay=100ms)
- **Autocomplete dropdown** ✅ — `.inpost-search__item-list.point` click
- **Map list click** ✅ — `a.list-point-link` zawierający kod paczkomatu
- **"Wybierz" popup** ✅ — klik leaf element z text="wybierz" w `.widget-modal`
- **#inpost_code** ✅ — wypełnione prawidłowo po kliknięciu "Wybierz"
- **Blik radio** ✅ — `input[name="payment"][value="25"]` force=True
- **Tab 1 → Tab 2** ✅ — `.js-cart-next` force=True
- **Regulamin** ✅ — `input[name="rules"]` force=True
- **Tab 2 → Tab 3** ✅ — `.js-cart-next` force=True
- **Zamawiam i płacę** ✅ — klik submit → redirect tpay.com
- **Logout + fresh session** ✅ — /wyloguj + nowy browser context per konto
- **Trigger** ✅ — podpięty w detector.py, batch mode (30th keywords)

### Paczkomat produkcyjny: PAD04M
### Paczkomat testowy: WAW65N (w test_full_flow.py)

### Konta:
- esemento@gmail.com (Tomasz Szczepaniak)
- blackmat36@gmail.com (Natalia Szczepaniak)
- tjbtaniojuzbylo@gmail.com (Jagoda Kaczmarek)
- y24015411@gmail.com (Miroslawa Szczepaniak)
- TEST: t11008543@gmail.com (Marian Wasilewski) — ZFLAGOWANE, cena 0 PLN

### Trigger keywords (30th):
- "30th", "30 celebration", "30-lecie", "30 lecie", "30 rocznica"

### Pliki:
- `/opt/pokemon-monitor-v2/tcgumisia_autobuy.py` — główny bot
- `/opt/pokemon-monitor-v2/tcgumisia_trigger.py` — trigger (30th keywords, batch mode)
- `/opt/pokemon-monitor-v2/test_full_flow.py` — test script (konto testowe)
- `/opt/pokemon-monitor-v2/detector.py` — wired: check_tcgumisia_trigger + flush_tcgumisia_batch

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
