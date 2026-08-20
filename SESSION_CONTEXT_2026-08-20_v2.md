# Session Context — 2026-08-20 v2 (Torpedo + Scraper Fixes)

## ZASTĘPUJE: SESSION_CONTEXT_2026-08-20.md

---

## ⚠️ OBOWIĄZKOWE NA START KAŻDEJ NOWEJ SESJI

```
cd /opt/pokemon-monitor-v2 && bash infra/live_report.sh && curl -sF 'file=@/tmp/live_report.txt' https://paste.rs
```

---

## Co zrobiono w tej sesji:

### 1. Scraper Fixes

| Fix | Opis |
|-----|------|
| **pokebeast.py** | REWRITE: Shoper → WooCommerce Store API (`/wp-json/wc/store/v1/products?category=16`). Sklep zmienił platformę. |
| **main.py** | CF Bridge warmup: `_ensure_browser()` przed startem shopów. Eliminuje cooldown cascade po restarcie. |
| **main.py** | Grace period 180s: pierwsze 3 min po starcie nie triggeruje cooldownu (daje czas na stabilizację). |
| **bastacentershop.py** | SHOP_DISABLED (kategoria pusta na stronie) |

### 2. JC Torpedo Daemon — INSTANT BUY (~3s)

**Plik:** `jc_torpedo_daemon.py`
**Service:** `jc-torpedo.service` (systemd, enabled, running)

**Architektura (potwierdzona testami — 3 zamówienia złożone!):**
- 1 patchright browser, 4 konteksty (osobna sesja per konto)
- Każde konto pre-staged na `/order` (BLIK + Kurier Inpost + checkboxes)
- Self-poll produktu 9419 co 4-7s (random jitter)
- Na restock: API cart swap + klik submit = **~3s na 4 konta parallel**

**Odkryte Sky-Shop API:**
- Login: `POST /login` (email, password, autologin, csrf_token)
- Cart: `GET /proxy_public_api?endpoint=/sky2/api-public/carts/bulk/latest`
- ATC: `POST /proxy_public_api?endpoint=/sky2/api-public/carts/{cart_id}/items` body: `{"productId":X,"quantity":1,"parameters":[]}`
- Cart item delete: `DELETE /proxy_public_api?endpoint=/sky2/api-public/carts/{cart_id}/items/{item_id}`
- Stock check = ATC attempt (200=available, 400=OOS `ERROR_PRODUCT_OUT_OF_STOCK`)
- Order page: `POST /order` body: `cart_id={id}` → HTML z csrf + payment/shipment
- Submit: `POST /order_finish/` (za Cloudflare — wymaga browser)

**Kluczowe ustalenia:**
- `/cart/add/{id}` (GET) NIE dodaje do koszyka w browser context (tylko w aiohttp)
- ATC musi iść przez Sky-Shop internal API (`/proxy_public_api?endpoint=...`)
- `/order_finish/` za CF (403 pure HTTP) → submit MUSI być przez browser
- csrf_token renderowany client-side (Angular) — nie da się wyciągnąć pure HTTP
- Pre-staged checkout: po API cart swap (clear+ATC), submit button działa BEZ reload
- Shipment ID: `6512b` (Kurier Inpost Gabaryt C) — stały
- Payment ID: `21` (BLIK) — stały

**Safety:**
- 1x per konto per produkt (japancollectibles_completed.json)
- Re-stage co 30 min (fresh csrf + sesja)
- Heartbeat co 5 min (keep-alive)
- Poll interval 5s + random jitter (4-7s) — bezpieczne, nie wygląda jak bot
- Fallback stage products: [7437, 7589, 9332, 9334] — użyj pierwszy dostępny
- Auto-restart (systemd RestartSec=30)

**Trigger flow:**
```
Self-poll (primary):
  co 4-7s: clear cart → ATC 9419 → 200? FIRE! : re-add stage product

Backup (scraper):
  japancollectibles_trigger.py → echo "9419" > /tmp/jc_torpedo_fire.txt
```

**Monitoring:**
```bash
sudo systemctl status jc-torpedo
journalctl -u jc-torpedo --since "5 min ago" --no-pager
```

---

## Pliki zmienione/dodane:

### Scrapers:
- `shops/pokebeast.py` — REWRITE (WooCommerce API)
- `shops/bastacentershop.py` — SHOP_DISABLED
- `main.py` — CF Bridge warmup + grace period 180s

### Torpedo:
- `jc_torpedo_daemon.py` — NOWY (daemon z self-poll + instant buy)
- `japancollectibles_torpedo.py` — starsza wersja (nadal w repo, nieużywana)
- `japancollectibles_trigger.py` — zmieniony (pisze do /tmp/jc_torpedo_fire.txt)
- `infra/jc-torpedo.service` — NOWY (systemd)
- `infra/deploy_torpedo.sh` — NOWY (deploy script)
- `infra/sniff_jc_checkout.py` — NOWY (network sniff tool)
- `infra/test_oos_atc.py` — NOWY (test ATC na OOS)
- `infra/test_prestaged_submit.py` — NOWY (test pre-staged submit)
- `infra/test_torpedo.sh` — zaktualizowany
- `infra/test_torpedo_push.sh` — zaktualizowany

### Diagnostyka:
- `torpedo_test_output.txt` — ostatni test output (do usunięcia)
- `torpedo_sniff.json` — sniff data (do usunięcia)
- `torpedo_cart_dump.html` — HTML dump (do usunięcia)

---

## Stan systemu:

| Service | Status | Uwagi |
|---------|--------|-------|
| pokemon-monitor-v2 | ✅ running | 140 shops, 15k scans/h |
| jc-torpedo | ✅ running | Polluje 9419, 4 konta staged |
| discord-router | ✅ running | Bez zmian |

| Metryka | Wartość |
|---------|---------|
| Load | 4-5 |
| RAM used | ~4.5GB/7.7GB (monitor + torpedo) |
| Chrome | ~44 procesów (39 monitor + 5 torpedo) |
| Torpedo RAM | ~230MB |
| Torpedo CPU | ~0% idle |

---

## Triggery (BEZ ZMIAN + torpedo):
- kartexpol, tantis, empik, smyk, japancollectibles, jc_30th, mediaexpert, strefatcg (max 1501 PLN), tcgumisia (ONLY ETB 30th < 410 PLN)
- **JC TORPEDO**: self-poll 9419, fire on restock (~3s)

---

## Znane problemy:

| Problem | Status | Priority |
|---------|--------|----------|
| bonito/proshop — IP blocked | SHOP_DISABLED | LOW |
| mediaexpert GraphQL 404 | Fallback goto działa | LOW |
| bastacentershop — pusta kategoria | SHOP_DISABLED | MONITOR |
| Torpedo: stage product OOS | Fallback list (4 produkty) | LOW |
| Torpedo: poll rate limit? | 5s + jitter = bezpieczne | MONITOR |

---

## Komendy:

```bash
# Monitor
sudo systemctl restart pokemon-monitor-v2
journalctl -u pokemon-monitor-v2 --since "5 min ago" --no-pager

# Torpedo
sudo systemctl status jc-torpedo
sudo systemctl restart jc-torpedo
journalctl -u jc-torpedo --since "5 min ago" --no-pager

# Manual fire (test)
DISPLAY=:99 ./venv/bin/python3 jc_torpedo_daemon.py --test --fire 7437

# Manual fire (production)
echo "9419" > /tmp/jc_torpedo_fire.txt
```
