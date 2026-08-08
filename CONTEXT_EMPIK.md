## Empik Auto-Buy Bot - GOTOWY (Aug 7 2026)
- Path: /opt/pokemon-monitor-v2/empik_autobuy.py
- Trigger: /opt/pokemon-monitor-v2/empik_trigger.py
- Scraper: /opt/pokemon-monitor-v2/shops/empik.py (Patchright + proxy, łapie ALL marketplace+empik)
- Completed: /opt/pokemon-monitor-v2/empik_completed.json
- Logs: empik_autobuy.log + empik_autobuy_stdout.log + empik_autobuy_stderr.log
- **POTWIERDZONE: zamówienie #10 1023 7318 4497 złożone, multi-account 2/2 TEST_OK**
- Method: nodriver + mobile proxy, CF Turnstile auto-resolves
- 20 kont (twanesek1-20@gmail.com / Senseye.)
- Flow: direct login (25s) → clear cart (checkboxy+Usuń zaznaczone) → ATC button click ×3 → proceed → PACKSTATION → InPost chip → search PAD04M → click point → BLIK input (data-ta="blik-input") → "Płacę Blikiem" → zamówienie
- Trigger: WATCH_PIDS + stock="empik" + price <= max + available
- WATCH_PIDS: {"1756071234": 160} (FP3 ≤160zł)
- Reaguje na: NEW_PRODUCT, RESTOCK, PRICE_CHANGE
- Qty: 3/konto, max 60 (20×3), stop na SOLD OUT lub konto 20
- DC notify po trigger
- Komendy: rm -f empik_completed.json && DISPLAY=:99 venv/bin/python3 -u empik_autobuy.py --max 60 --qty 3 --start 1 "URL"
- Dodanie PID: sed -i '/WATCH_PIDS = {/a\    "PID": CENA,' empik_trigger.py && sudo systemctl restart pokemon-monitor-v2
### Empik scraper (Aug 7):
- Patchright headless=False + proxy, CF bypass
- Łapie WSZYSTKO (marketplace + empik-own) - żeby widzieć ID
- stock="empik" (shopId=0) lub "marketplace_XXX"
- 259 produktów w teście
- W PW_SHOPS orchestratora (90-180s delay)
## SMYK Auto-Buy Bot (UPDATED Aug 7 2026)
- Path: /opt/pokemon-monitor-v2/smyk_autobuy.py
- Trigger: smyk_trigger.py
- 4 konta, 12 szt/konto
- Flow: Login → Clear cart → ATC ×12 → DPD → BLIK 654654 → Zamów
- Trigger keywords: "first partner", "illustration collection", "30th", "30 anniversary", "30 lecie", "30 rocznica"
- Cena: FP3/illustration ≤160zł, 30th BEZ limitu ceny
- Reaguje na: NEW_PRODUCT, RESTOCK, PRICE_CHANGE
- DC notify po trigger
- Sprawdzony: 3/4 zamówienia (Aug 4), teraz produkt niedostępny (button NOT FOUND = correct)
## Tantis Auto-Buy Bot (UPDATED Aug 7)
- GOTOWY, DRY RUN OK w 14s
- 4 konta, FP3 ×2, 30th ×1
- Patchright + page.evaluate(fetch())
- Reaguje na: NEW_PRODUCT, RESTOCK, PRICE_CHANGE
- DC notify po trigger
## Kartexpol Auto-Buy Bot (UPDATED Aug 7)
- GOTOWY, pure aiohttp <3s/konto
- 4 konta, 1 szt per produkt
- Trigger: "30" w nazwie
- Reaguje na: NEW_PRODUCT, RESTOCK, PRICE_CHANGE
- UWAGA: --test flag nie działa poprawnie (składa prawdziwe zamówienia!)
- DC notify po trigger
## BoosterPoint Auto-Buy Bot (UPDATED Aug 7)
- GOTOWY, DRY RUN 4/4 OK
- 4 konta, 2 (ETB) / 1 (rest)
- aiohttp + proxy
- Trigger: 30th keywords
- Reaguje na: NEW_PRODUCT, RESTOCK, PRICE_CHANGE
- DC notify po trigger
- User płaci ręcznie (BLIK wymaga prawdziwego kodu)
## Trigger Guards - PEŁNA TABELA (Aug 7 2026)
| Sklep | Kont | Qty | Keywords/PIDs | Cena | Events |
|-------|------|-----|---------------|------|--------|
| empik | 20 | 3 | PID 1756071234 | ≤160 | NEW+RESTOCK+PRICE_CHANGE |
| smyk | 4 | 12 | FP/illustration/30th | FP≤160, 30th=∞ | NEW+RESTOCK+PRICE_CHANGE |
| tantis | 4 | 2/1 | FP3/30th | FP<160, 30th=∞ | NEW+RESTOCK+PRICE_CHANGE |
| kartexpol | 4 | 1 | "30" w nazwie | ∞ | NEW+RESTOCK+PRICE_CHANGE |
| boosterpoint | 4 | 2/1 | 30th keywords | ∞ | NEW+RESTOCK+PRICE_CHANGE |
## Integration detector.py (Aug 7):
```python
from smyk_trigger import check_smyk_autobuy
from kartexpol_trigger import check_kartexpol_autobuy
from tantis_trigger import check_tantis_trigger
from boosterpoint_trigger import check_boosterpoint_trigger
from empik_trigger import check_empik_trigger
# On NEW_PRODUCT:
check_smyk_autobuy(shop_name, "NEW_PRODUCT", product)
check_kartexpol_autobuy(shop_name, "NEW_PRODUCT", product, kartexpol_batch)
check_tantis_trigger("NEW_PRODUCT", product)
check_boosterpoint_trigger("NEW_PRODUCT", product)
check_empik_trigger("NEW_PRODUCT", product)
# On RESTOCK:
check_smyk_autobuy(shop_name, "RESTOCK", product)
check_kartexpol_autobuy(shop_name, "RESTOCK", product, kartexpol_batch)
check_tantis_trigger("RESTOCK", product)
check_boosterpoint_trigger("RESTOCK", product)
check_empik_trigger("RESTOCK", product)
# On PRICE_CHANGE:
check_smyk_autobuy(shop_name, "PRICE_CHANGE", product)
check_kartexpol_autobuy(shop_name, "PRICE_CHANGE", product, kartexpol_batch)
check_tantis_trigger("PRICE_CHANGE", product)
check_boosterpoint_trigger("PRICE_CHANGE", product)
check_empik_trigger("PRICE_CHANGE", product)
```
## Konta empik (20 szt, Aug 7):
- twanesek1-20@gmail.com / Senseye. (z kropką)
- twanesek1-10: istniejące, twanesek11-20: zarejestrowane fresh
- Adres: Tomasz Szczepaniak, Leśna 46a/2, 62-069 Palędzie, +48 607 183 797
- Paczkomat: PAD04M (Żurawinowa 9, Palędzie)
## Reset completed (pozwala kupić ponownie):
```
rm -f empik_completed.json smyk_completed.json tantis_completed.json boosterpoint_completed.json
```
## Empik bot - komendy:
- Test 1 konto: rm -f empik_completed.json && DISPLAY=:99 timeout 180 venv/bin/python3 -u empik_autobuy.py --test --max 1 --qty 1 --start 1 "URL" 2>&1 | sed 's/127\.0\.0\.1:8888/PROXY/g'
- Produkcja all: rm -f empik_completed.json && DISPLAY=:99 venv/bin/python3 -u empik_autobuy.py --max 60 --qty 3 --start 1 "URL"
- Dodanie PID: sed -i '/WATCH_PIDS = {/a\    "NOWY_PID": MAX_CENA,' empik_trigger.py
- Logi: tail -30 empik_autobuy.log
- Scraper: sudo journalctl -u pokemon-monitor-v2 --since "3 min ago" --no-pager | grep empik
