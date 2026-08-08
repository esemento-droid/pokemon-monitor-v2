#!/usr/bin/env python3
"""
BoosterPoint.pl - Bot 30-lecie Pokemon
Monitoruje produkty, dodaje do koszyka, wysyła linki do opłacenia.

Flow:
1. Monitoruje WC Store API co 5s
2. Jak wykryje produkty 30-lecia in stock:
   - Loguje się na każde konto
   - Dodaje produkty (2x ETB, 1x reszta)
   - Wybiera InPost Kurier
   - Wysyła na Discord link do checkout
3. User klika link → BLIK → gotowe (10s per konto)

Config: boosterpoint_config.json
Webhook: z .env (DISCORD_WEBHOOK)
"""

import asyncio
import aiohttp
import json
import re
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bp30")

BASE_DIR = Path("/opt/pokemon-monitor-v2")
load_dotenv(BASE_DIR / ".env")

BASE = "https://boosterpoint.pl"
STORE_API = f"{BASE}/wp-json/wc/store/v1"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")

CONFIG = {}
COMPLETED_FILE = BASE_DIR / "boosterpoint_completed.json"


def load_config():
    global CONFIG
    cfg_path = BASE_DIR / "boosterpoint_config.json"
    if not cfg_path.exists():
        log.error(f"Brak configu: {cfg_path}")
        sys.exit(1)
    CONFIG = json.loads(cfg_path.read_text())
    log.info(f"Config: {len(CONFIG['accounts'])} kont")


def load_completed():
    if COMPLETED_FILE.exists():
        return json.loads(COMPLETED_FILE.read_text())
    return {}


def save_completed(completed):
    COMPLETED_FILE.write_text(json.dumps(completed, indent=2))


def parse_wc(text):
    for c in ['{', '[']:
        idx = text.find(c)
        if idx >= 0:
            try:
                return json.loads(text[idx:])
            except:
                pass
    return None


async def discord_notify(session, msg, color=0x00FF00):
    if not DISCORD_WEBHOOK:
        return
    try:
        await session.post(DISCORD_WEBHOOK, json={
            "embeds": [{
                "title": "🛒 BoosterPoint 30-lecie",
                "description": msg[:4000],
                "color": color,
            }]
        })
    except Exception as e:
        log.error(f"Discord: {e}")


def get_qty_for_product(product):
    """2x dla ETB, 1x dla reszty."""
    name = product.get("name", "").lower()
    if "etb" in name or "elite trainer" in name or "elite-trainer" in name:
        return CONFIG.get("quantity_etb", 2)
    return 1


async def search_30th_products(session):
    """Szukaj produktów 30-lecia in stock."""
    found = []
    keywords = CONFIG.get("keywords", ["30th", "anniversary", "30-lecie", "celebrations"])

    for term in keywords:
        try:
            async with session.get(f"{STORE_API}/products?per_page=100&search={term}") as r:
                if r.status != 200:
                    continue
                text = await r.text()
                data = parse_wc(text)
                if not data or not isinstance(data, list):
                    continue
                for p in data:
                    if p.get("is_in_stock") and p["id"] not in [x["id"] for x in found]:
                        found.append(p)
        except Exception as e:
            log.debug(f"Search '{term}': {e}")

    # Check newest products
    try:
        async with session.get(f"{STORE_API}/products?per_page=50&orderby=date&order=desc") as r:
            if r.status == 200:
                text = await r.text()
                data = parse_wc(text)
                if data and isinstance(data, list):
                    for p in data:
                        if not p.get("is_in_stock"):
                            continue
                        name = p.get("name", "").lower()
                        if any(kw.lower() in name for kw in keywords):
                            if p["id"] not in [x["id"] for x in found]:
                                found.append(p)
    except:
        pass

    return found


async def prepare_cart_on_account(account, products):
    """
    Loguje się, czyści koszyk, dodaje produkty, wybiera shipping.
    Zwraca True jeśli koszyk gotowy do opłacenia.
    """
    email = account["email"]
    password = account["password"]

    try:
        jar = aiohttp.CookieJar()
        async with aiohttp.ClientSession(headers={"User-Agent": UA}, cookie_jar=jar) as s:
            # === LOGIN ===
            async with s.get(f"{BASE}/moje-konto/") as r:
                text = await r.text()
                m = re.search(r'name="woocommerce-login-nonce"\s+value="([^"]+)"', text)
                if not m:
                    log.error(f"[{email}] Brak login nonce")
                    return False
                login_nonce = m.group(1)

            async with s.post(f"{BASE}/moje-konto/", data={
                "username": email,
                "password": password,
                "woocommerce-login-nonce": login_nonce,
                "_wp_http_referer": "/moje-konto/",
                "login": "Zaloguj się",
                "rememberme": "forever",
            }, allow_redirects=True) as r:
                text = await r.text()
                if "Invalid login" in text or ("woocommerce-error" in text and "nieprawidł" in text.lower()):
                    log.error(f"[{email}] ✗ Login failed")
                    return False
                log.info(f"[{email}] ✓ Zalogowano")

            # === STORE API SESSION ===
            async with s.get(f"{STORE_API}/cart") as r:
                nonce = r.headers.get("nonce", "")
                cart_token = r.headers.get("cart-token", "")
                if not nonce:
                    log.error(f"[{email}] Brak store nonce")
                    return False
                text = await r.text()
                cart = parse_wc(text)

            hdrs = {"Nonce": nonce, "Cart-Token": cart_token}

            # === CLEAR CART ===
            if cart and cart.get("items_count", 0) > 0:
                for item in cart.get("items", []):
                    async with s.post(f"{STORE_API}/cart/remove-item",
                                      json={"key": item["key"]}, headers=hdrs) as r:
                        nonce = r.headers.get("nonce", nonce)
                        hdrs["Nonce"] = nonce
                log.info(f"[{email}] Koszyk wyczyszczony")

            # === ADD PRODUCTS ===
            added = []
            for p in products:
                qty = get_qty_for_product(p)
                async with s.post(f"{STORE_API}/cart/add-item",
                                  json={"id": p["id"], "quantity": qty},
                                  headers=hdrs) as r:
                    nonce = r.headers.get("nonce", nonce)
                    hdrs["Nonce"] = nonce
                    if r.status == 201:
                        added.append((p, qty))
                        log.info(f"[{email}] ✓ +{qty}x {p['name']}")
                    else:
                        text = await r.text()
                        data = parse_wc(text)
                        msg = data.get("message", "") if data else ""
                        log.warning(f"[{email}] ✗ {p['name']}: {msg[:60]}")
                await asyncio.sleep(0.2)

            if not added:
                log.error(f"[{email}] Nie dodano żadnego produktu")
                return False

            # === SELECT SHIPPING ===
            rate = CONFIG.get("shipping_rate", "flat_rate:15")
            async with s.post(f"{STORE_API}/cart/select-shipping-rate",
                              json={"package_id": 0, "rate_id": rate},
                              headers=hdrs) as r:
                nonce = r.headers.get("nonce", nonce)
                hdrs["Nonce"] = nonce
                if r.status == 200:
                    log.info(f"[{email}] ✓ Wysyłka: InPost Kurier")

            # === UPDATE BILLING/SHIPPING ADDRESS ===
            billing = account.get("billing", {})
            billing["email"] = email
            shipping = account.get("shipping", {})

            async with s.post(f"{STORE_API}/cart/update-customer",
                              json={
                                  "billing_address": billing,
                                  "shipping_address": shipping,
                              },
                              headers=hdrs) as r:
                nonce = r.headers.get("nonce", nonce)
                hdrs["Nonce"] = nonce
                if r.status == 200:
                    log.info(f"[{email}] ✓ Adres ustawiony")

            # === VERIFY CART ===
            async with s.get(f"{STORE_API}/cart", headers=hdrs) as r:
                text = await r.text()
                cart = parse_wc(text)
                items_count = cart.get("items_count", 0) if cart else 0
                if items_count > 0:
                    prods_str = ", ".join([f"{qty}x {p['name']}" for p, qty in added])
                    log.info(f"[{email}] ✅ KOSZYK GOTOWY: {prods_str}")
                    return True
                else:
                    log.error(f"[{email}] Koszyk pusty po dodaniu?!")
                    return False

    except Exception as e:
        log.error(f"[{email}] Exception: {e}")
        return False


async def main():
    load_config()
    completed = load_completed()

    accounts = CONFIG["accounts"]
    poll_interval = CONFIG.get("poll_interval", 5)
    dry_run = "--dry-run" in sys.argv

    log.info(f"BoosterPoint 30-lecie Bot")
    log.info(f"Kont: {len(accounts)}, Poll: {poll_interval}s, Webhook: {'✓' if DISCORD_WEBHOOK else '✗'}")
    log.info(f"ETB qty: {CONFIG.get('quantity_etb', 2)}, reszta: 1")
    if dry_run:
        log.info("=== DRY RUN ===")

    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
        await discord_notify(session,
            f"🟢 BoosterPoint bot start. {len(accounts)} kont. Monitoruję drop 30-lecia...",
            color=0x3498DB)

        cycle = 0
        while True:
            cycle += 1
            try:
                products = await search_30th_products(session)
                in_stock = [p for p in products if p.get("is_in_stock")]

                if in_stock:
                    # Filter out already completed
                    new_products = []
                    for p in in_stock:
                        # If ALL accounts have this product, skip
                        all_have = all(
                            p["id"] in completed.get(acc["email"], [])
                            for acc in accounts
                        )
                        if not all_have:
                            new_products.append(p)

                    if not new_products:
                        if cycle % 12 == 1:
                            log.info(f"[Cycle {cycle}] Produkty 30-lecia znalezione ale już kupione. Czekam na nowe...")
                        await asyncio.sleep(poll_interval)
                        continue

                    log.info(f"[Cycle {cycle}] 🚨 {len(new_products)} NOWYCH produktów 30-lecia!")
                    for p in new_products:
                        price = int(p["prices"]["price"]) / 100
                        qty = get_qty_for_product(p)
                        log.info(f"  → {qty}x {p['name']} | {price:.2f} zł")

                    prods_str = "\n".join([f"• {get_qty_for_product(p)}x {p['name']}" for p in new_products])
                    await discord_notify(session,
                        f"🚨 **DROP 30-LECIE WYKRYTY!**\n\n{prods_str}\n\nPrzygotowuję koszyki...",
                        color=0xFF6600)

                    if not dry_run:
                        # Prepare cart on each account
                        ready_accounts = []
                        for acc in accounts:
                            # Skip if all products already bought on this account
                            acc_products = [p for p in new_products if p["id"] not in completed.get(acc["email"], [])]
                            if not acc_products:
                                log.info(f"[{acc['email']}] Wszystko kupione ✓")
                                continue

                            ok = await prepare_cart_on_account(acc, acc_products)
                            if ok:
                                ready_accounts.append(acc)
                                # Mark as completed
                                if acc["email"] not in completed:
                                    completed[acc["email"]] = []
                                for p in acc_products:
                                    completed[acc["email"]].append(p["id"])
                                save_completed(completed)
                            await asyncio.sleep(1)

                        # Send checkout links
                        if ready_accounts:
                            links = "\n".join([
                                f"• **{acc['email']}** → [OPŁAĆ]({BASE}/zamowienie/)"
                                for acc in ready_accounts
                            ])
                            await discord_notify(session,
                                f"✅ **KOSZYKI GOTOWE!**\n\n{links}\n\n"
                                f"Zaloguj się na każde konto i wejdź w:\n"
                                f"**{BASE}/zamowienie/**\n"
                                f"→ Wybierz BLIK → Wpisz kod → Gotowe!",
                                color=0x00FF00)
                            log.info(f"✅ {len(ready_accounts)} koszyków gotowych do opłacenia!")
                        else:
                            log.warning("Żadne konto nie zostało przygotowane")

                else:
                    if cycle % 12 == 1:
                        log.info(f"[Cycle {cycle}] Brak produktów 30-lecia. Czekam...")

            except Exception as e:
                log.error(f"[Cycle {cycle}] {e}")
                if "503" in str(e):
                    await asyncio.sleep(10)

            await asyncio.sleep(poll_interval)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Bot zatrzymany (Ctrl+C)")
    except Exception as e:
        log.error(f"Fatal: {e}")
