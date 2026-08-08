# Session Context — Pokemon Monitor v2
## Last updated: 2026-08-08

---

## AKTYWNE BOTY AUTO-BUY (uzbrojone, gotowe na drop):

### 1. Kartexpol (NOWY — 2026-08-08)
- **Plik:** `/opt/pokemon-monitor-v2/kartexpol_autobuy.py`
- **Trigger:** `/opt/pokemon-monitor-v2/kartexpol_trigger.py`
- **Metoda:** Patchright headless=False + mobile proxy (`127.0.0.1:8888`)
- **Flow:** Login → ATC → Checkout single-page (paczkomat + BLIK + zgody) → "Zamawiam i płacę" → Autopay redirect
- **Konta:** 4 produkcyjne (esemento, blackmat36, tjbtaniojuzbylo, y24015411) + 1 test (t11008543)
- **Hasła:** takie same jak strefa-tcg
- **Trigger keywords:** "30th", "30 celebration", "30-lecie", "30 lecie", "30 rocznica"
- **Completed tracking:** `kartexpol_completed.json`
- **Discord:** `discord_webhook_kartexpol.txt`
- **Platforma:** Shoper (kartexpol.pl) — ALE inny layout niż strefa-tcg:
  - Login: `input[name="email"]` + `input[name="password"]` + klik button "Zaloguj się"
  - Checkout: SINGLE PAGE `/pl/basket/step2` (nie multi-step!)
  - Paczkomat: `input[name="nearest_pickup_point"]` (klik pierwszy radio)
  - Płatność BLIK: `input[name="basket_payment"][value="3:509"]`
  - Zgody: `additional_2` (regulamin sklepu) + dynamiczny (regulamin Paczkomat 24/7) — skip "faktur"
  - Submit: `button.btn_primary.btn_full-width` ("Zamawiam i płacę") — MUSI być force=True (consent modal blokuje)
  - Koszyk: per-sesja (nowy context = pusty koszyk, nie trzeba czyścić)
- **Test:** `DISPLAY=:99 /opt/pokemon-monitor-v2/venv/bin/python3 kartexpol_autobuy.py --test https://www.kartexpol.pl/pl/p/Jakis-Produkt/ID`
- **Status:** ✅ DZIAŁA, przetestowane 2026-08-08 (zamówienie #328, #329 na Autopay)

### 2. Strefa-TCG
- **Plik:** `/opt/pokemon-monitor-v2/strefatcg_autobuy.py`
- **Metoda:** Patchright headless=False (BEZ proxy — TODO: dodać)
- **Flow:** Login → Clear cart → ATC → 3-step checkout (ZAMAWIAM → paczkomat+checkboxy → PODSUMOWANIE → POTWIERDZAM) → Przelewy24
- **Konta:** 4 produkcyjne + 1 test (te same co kartexpol)
- **Platforma:** Shoper (strefa-tcg.pl) — starsza wersja:
  - Login: `input[name="mail"]` + `input[name="pass"]` + `form.submit()`
  - Checkout: 3-step (step2, step3)
  - Koszyk: `a.prodremove` do czyszczenia

### 3. Empik
- **Plik:** `/opt/pokemon-monitor-v2/empik_autobuy.py`
- **Metoda:** nodriver + mobile proxy (`127.0.0.1:8888`)
- **Konta:** 20 (twanesek1-20@gmail.com)
- **Status:** ✅ DZIAŁA

### 4. Tantis
- **Plik:** `/opt/pokemon-monitor-v2/tantis_autobuy.py`
- **Metoda:** Patchright batch mode (BEZ proxy — TODO: dodać)
- **Konta:** 4

### 5. Smyk
- **Plik:** `/opt/pokemon-monitor-v2/smyk_autobuy.py`
- **Metoda:** Playwright (BEZ proxy — TODO: dodać)
- **Konta:** 4 × 12 szt

### 6. JapanCollectibles (30th batch)
- **Plik:** `/opt/pokemon-monitor-v2/japancollectibles_autobuy_30th.py`
- **Metoda:** Patchright (BEZ proxy — TODO: dodać)
- **Konta:** 4
- **Submit button:** `button[name="finish"]` (uwaga: inne niż kartexpol!)

---

## JAK ROBIĆ NOWE BOTY (pattern):

### 1. Debug login page
```bash
# Sprawdź selektory formularza logowania
DISPLAY=:99 venv/bin/python3 debug_login.py
```
Szukaj: name inputów email/password, typ submit buttona, czy to modal czy strona.

### 2. Debug checkout page
```bash
# Sprawdź radios, checkboxy, buttony na checkout
DISPLAY=:99 venv/bin/python3 debug_checkout.py
```
Szukaj: name radio buttons (dostawa, paczkomat, płatność), wymagane checkboxy, tekst submit buttona.

### 3. Kluczowe zasady:
- **Shoper platform:** Każdy sklep na Shoper ma INNY layout mimo tego samego silnika!
- **Nie zakładaj że strefa-tcg = inne sklepy Shoper** — zawsze debug selektory
- **Vue/React components:** `form.submit()` NIE DZIAŁA — zawsze klikaj button przez PW `force=True`
- **Consent modal blokuje kliknięcia:** Zawsze `dismiss_overlay()` przed submit (usuwaj h-portal-target, consents-modal)
- **Koszyk per-sesja:** Nowy browser context = pusty koszyk (nie trzeba czyścić)
- **Proxy:** Dodaj `--proxy-server=http://127.0.0.1:8888` do browser args
- **Test:** Zawsze `--test` flag z kontem `t11008543@gmail.com` (nie markuje completed, nie spamuje DC)

### 4. Flow tworzenia bota:
1. Sprawdź scraper (`shops/SKLEP.py`) — jakie produkty, jakie URLe
2. Debug login (selektory formularza)
3. Debug checkout (co trzeba kliknąć/zaznaczyć)
4. Napisz bot (wzoruj na `kartexpol_autobuy.py` — najnowszy pattern)
5. Napisz trigger (wzoruj na `kartexpol_trigger.py`)
6. Podepnij w `detector.py`
7. Test: `--test` na koncie testowym
8. Deploy: `git pull && sudo systemctl restart pokemon-monitor-v2`

---

## TODO — PRZEROBIĆ NA PROXY:

Następujące boty NIE idą przez proxy i powinny zostać przerobione:
1. **strefatcg_autobuy.py** — dodać `--proxy-server=http://127.0.0.1:8888`
2. **tantis_autobuy.py** — dodać proxy
3. **smyk_autobuy.py** — dodać proxy
4. **japancollectibles_autobuy_30th.py** — dodać proxy
5. **japancollectibles_autobuy.py** — dodać proxy

Wystarczy dodać do browser launch args:
```python
args=[..., '--proxy-server=http://127.0.0.1:8888']
```

---

## Mobile Proxy (aktywne):
- **Lokalne:** `127.0.0.1:8888` (tinyproxy na VPS)
- **Routing:** VPS → WireGuard → Xiaomi → Orange PL LTE
- **Dane:** 800GB Orange
- **Watchdog:** cron sprawdza czy proxy żyje
- **Używają:** empik_autobuy.py, kartexpol_autobuy.py, scrapery (basanti, bookland, empik, epiccard, pikashop)

---

## Komendy VPS:

Zawsze z venv i DISPLAY:
```bash
# Test bota:
DISPLAY=:99 /opt/pokemon-monitor-v2/venv/bin/python3 SKRYPT.py --test URL

# Restart serwisu:
sudo systemctl restart pokemon-monitor-v2

# Logi:
tail -f /opt/pokemon-monitor-v2/kartexpol_autobuy.log
journalctl -u pokemon-monitor-v2 -f

# Git pull + restart:
cd /opt/pokemon-monitor-v2 && git fetch origin && git reset --hard origin/main && sudo systemctl restart pokemon-monitor-v2
```

---

## Interakcja z Kiro (w tej sesji):
- Komendy do VPS: zawsze pipe `2>&1 | curl -s -d @- https://paste.rs/`
- User wkleja URL paste.rs → Kiro fetchuje wynik
- Multiline komendy: zapisz jako .py na repo, push, user pulluje i odpala
- NIGDY nie dawaj `curl paste.rs | bash` — łamie się na multiline
