#!/usr/bin/env python3
"""
JC Torpedo — Pure HTTP instant buy (<2s for all 4 accounts)

Sky-Shop internal API discovered via network sniff:
  1. POST /login → session cookie
  2. GET /proxy_public_api?endpoint=/sky2/api-public/carts/bulk/latest → cart_id
  3. POST /proxy_public_api?endpoint=/sky2/api-public/carts/{cart_id} → ATC
  4. POST /order {cart_id} → HTML with csrf_token + shipment IDs
  5. POST /order_finish/ {csrf, payment=21(BLIK), shipment, checkboxes} → payment redirect

All HTTP. Zero browser. <2s total for 4 accounts parallel.
"""
import asyncio
import json
import logging
import os
import sys
import time
import re
from pathlib import Path

import aiohttp

BASE_DIR = Path("/opt/pokemon-monitor-v2")
COMPLETED_FILE = BASE_DIR / "japancollectibles_completed.json"
LOG_FILE = BASE_DIR / "jc_torpedo_daemon.log"
WEBHOOK_FILE = BASE_DIR / "discord_webhook_jc.txt"
SHOP_URL = "https://japancollectibles.shop"
FIRE_FILE = Path("/tmp/jc_torpedo_fire.txt")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [JC-TORPEDO] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

ACCOUNTS = [
    {"email": "esemento@gmail.com", "password": "cR!9GW#x2wqJtGw", "name": "Tomasz Szczepaniak"},
    {"email": "blackmat36@gmail.com", "password": "v2@pvDGt#ZuN3ui", "name": "Natalia Szczepaniak"},
    {"email": "tjbtaniojuzbylo@gmail.com", "password": "P9XAfQE.SCwFq5i", "name": "Jagoda Kaczmarek"},
    {"email": "y24015411@gmail.com", "password": "huw!e.twdCmv9@B", "name": "Mirosława Szczepaniak"},
]

TEST_ACCOUNT = {"email": "t11008543@gmail.com", "password": "mt!cSsphud4Zhnz", "name": "Marian Wasilewski"}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
PROXY = "http://127.0.0.1:8888"

# Payment IDs (from sniff): 21=BLIK, 15=online, 22=card, 5=przelew
PAYMENT_BLIK = "21"


async def torpedo_buy(account, product_id):
    """Pure HTTP buy. Target: <2s."""
    email = account["email"]
    password = account["password"]
    t0 = time.time()

    connector = aiohttp.TCPConnector(ssl=False)
    jar = aiohttp.CookieJar(unsafe=True)

    async with aiohttp.ClientSession(
        connector=connector,
        cookie_jar=jar,
        headers={"User-Agent": UA},
    ) as s:
        # === 1. LOGIN ===
        try:
            # Get login page first (for csrf + session cookie)
            r = await s.get(f"{SHOP_URL}/login", proxy=PROXY, timeout=aiohttp.ClientTimeout(total=8))
            login_html = await r.text()
            # Extract csrf_token from login page
            csrf_match = re.search(r'name="csrf_token"\s*value="([^"]+)"', login_html)
            csrf_login = csrf_match.group(1) if csrf_match else ""

            r = await s.post(
                f"{SHOP_URL}/login",
                data={"email": email, "password": password, "autologin": "1", "csrf_token": csrf_login, "redirect": "", "submit": "1"},
                proxy=PROXY,
                timeout=aiohttp.ClientTimeout(total=8),
                allow_redirects=True,
            )
            resp_text = await r.text()
            if "Moje konto" not in resp_text and "Wyloguj" not in resp_text:
                log.error(f"[{email}] Login FAILED ({time.time()-t0:.2f}s)")
                return False
            log.info(f"[{email}] Login OK ({time.time()-t0:.2f}s)")
        except Exception as e:
            log.error(f"[{email}] Login error: {e}")
            return False

        # === 2. GET CART ID ===
        try:
            r = await s.get(
                f"{SHOP_URL}/proxy_public_api?endpoint=/sky2/api-public/carts/bulk/latest",
                proxy=PROXY,
                timeout=aiohttp.ClientTimeout(total=5),
            )
            cart_data = await r.json()
            cart_id = cart_data.get("cart", {}).get("id", "")
            if not cart_id:
                log.error(f"[{email}] No cart_id")
                return False
            log.info(f"[{email}] Cart: {cart_id[:8]}... ({time.time()-t0:.2f}s)")
        except Exception as e:
            log.error(f"[{email}] Cart error: {e}")
            return False

        # === 3. CLEAR CART + ADD TO CART ===
        try:
            # Clear cart first (delete all existing items)
            r = await s.get(
                f"{SHOP_URL}/proxy_public_api?endpoint=/sky2/api-public/carts/bulk/{cart_id}",
                proxy=PROXY,
                timeout=aiohttp.ClientTimeout(total=5),
            )
            cart_check = await r.json()
            existing_items = cart_check.get("cart", {}).get("items", [])
            for item in existing_items:
                item_id = item.get("id", "")
                if item_id:
                    await s.delete(
                        f"{SHOP_URL}/proxy_public_api?endpoint=/sky2/api-public/carts/{cart_id}/items/{item_id}",
                        headers={"Accept": "application/json", "currency": "PLN", "lang": "pl"},
                        proxy=PROXY,
                        timeout=aiohttp.ClientTimeout(total=3),
                    )
            if existing_items:
                log.info(f"[{email}] Cleared {len(existing_items)} items from cart")

            # Add product
            r = await s.post(
                f"{SHOP_URL}/proxy_public_api?endpoint=/sky2/api-public/carts/{cart_id}/items",
                json={"productId": int(product_id), "quantity": 1, "parameters": []},
                headers={"Content-Type": "application/json;charset=UTF-8", "Accept": "application/json, text/plain, */*", "currency": "PLN", "lang": "pl", "Origin": SHOP_URL, "Referer": f"{SHOP_URL}/-p{product_id}"},
                proxy=PROXY,
                timeout=aiohttp.ClientTimeout(total=5),
            )
            if r.status != 200:
                body = await r.text()
                log.error(f"[{email}] ATC HTTP {r.status}: {body[:200]}")
                return False
            atc_text = await r.text()
            try:
                atc_data = json.loads(atc_text)
            except:
                log.error(f"[{email}] ATC not JSON: {atc_text[:300]}")
                return False

            # ATC response has "addedCartItem" (not "cart.items")
            added = atc_data.get("addedCartItem", {})
            if not added:
                log.error(f"[{email}] ATC no addedCartItem: {atc_text[:300]}")
                return False
            log.info(f"[{email}] ATC OK (product {product_id}, {added.get('priceSummary',{}).get('final',{}).get('grossDisplay','?')}) ({time.time()-t0:.2f}s)")
        except Exception as e:
            log.error(f"[{email}] ATC error: {e}")
            return False

        # === 4. GO TO ORDER PAGE (POST /order with cart_id) → get csrf + shipment ===
        try:
            r = await s.post(
                f"{SHOP_URL}/order",
                data={"cart_id": cart_id},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": SHOP_URL,
                    "Referer": f"{SHOP_URL}/cart/",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Upgrade-Insecure-Requests": "1",
                },
                proxy=PROXY,
                timeout=aiohttp.ClientTimeout(total=8),
                allow_redirects=True,
            )
            order_html = await r.text()
            log.info(f"[{email}] Order page: {len(order_html)} bytes, URL: {r.url}")

            # Extract csrf_token for order_finish
            csrf_match = re.search(r'name="csrf_token"\s*value="([^"]+)"', order_html)
            csrf_token = csrf_match.group(1) if csrf_match else ""

            # Extract shipment IDs
            shipment_ids = re.findall(r'name="shipment"[^>]*value="([^"{\[]+)"', order_html)
            if not shipment_ids:
                shipment_ids = re.findall(r'id="param-delivery-([^"]+)"', order_html)
            if not shipment_ids:
                # Try broader: any value in shipment section that looks like an ID
                shipment_ids = re.findall(r'shipment[^>]*value="(\w{3,})"', order_html)

            log.info(f"[{email}] Order page: csrf={'yes' if csrf_token else 'NO'}, shipments={shipment_ids[:3]} ({time.time()-t0:.2f}s)")

            if not csrf_token:
                # Maybe page didn't render properly — dump first 1000 chars for debug
                log.error(f"[{email}] No csrf! HTML start: {order_html[:500]}")
                return False

            shipment_id = shipment_ids[0] if shipment_ids else ""

        except Exception as e:
            log.error(f"[{email}] Order page error: {e}")
            return False

        # === 5. SUBMIT ORDER (POST /order_finish/) ===
        order_data = {
            "csrf_token": csrf_token,
            "payment": PAYMENT_BLIK,
            "shipment": shipment_id,
            "user_country": "PL",
            "register_link_to_rules": "1",
            "register_must_accept": "1",
            "dotpay_rules_agreed": "1",
            "is_js": "1",
            "code_discount": "",
            "gratis": "",
            "user_note": "",
        }

        try:
            r = await s.post(
                f"{SHOP_URL}/order_finish/",
                data=order_data,
                proxy=PROXY,
                timeout=aiohttp.ClientTimeout(total=10),
                allow_redirects=True,
            )
            final_url = str(r.url)
            final_text = await r.text()
            total = time.time() - t0

            # Check success
            success = any(kw in final_url.lower() for kw in ["potwierdzenie", "thank", "tpay", "blik", "przelewy24", "dotpay"])
            if not success:
                success = any(kw in final_text.lower() for kw in ["zamówienie zostało złożone", "dziękujemy", "potwierdzenie"])
            # Also: redirect away from /order = likely success
            if not success and "/order" not in final_url and "/cart" not in final_url:
                success = True

            if success:
                log.info(f"[{email}] ✅ ORDER PLACED in {total:.2f}s! → {final_url[:80]}")
                _mark_completed(product_id, email)
                return True
            else:
                log.error(f"[{email}] ❌ Order failed ({total:.2f}s) URL: {final_url[:80]}")
                # Check for error messages
                errors = re.findall(r'class="[^"]*error[^"]*"[^>]*>([^<]+)', final_text)
                if errors:
                    log.error(f"[{email}] Errors: {errors[:3]}")
                return False

        except Exception as e:
            log.error(f"[{email}] Submit error: {e}")
            return False


def _mark_completed(product_id, email):
    data = {}
    if COMPLETED_FILE.exists():
        try:
            data = json.loads(COMPLETED_FILE.read_text())
        except:
            pass
    pid = str(product_id)
    if pid not in data:
        data[pid] = []
    if email not in data[pid]:
        data[pid].append(email)
    COMPLETED_FILE.write_text(json.dumps(data, indent=2))


async def _send_discord(msg):
    try:
        if not WEBHOOK_FILE.exists():
            return
        wh = WEBHOOK_FILE.read_text().strip()
        if not wh:
            return
        async with aiohttp.ClientSession() as s:
            await s.post(wh, json={"content": msg})
    except:
        pass


async def fire(product_id, accounts):
    """Fire torpedo on all accounts in PARALLEL."""
    t0 = time.time()
    log.info(f"=== 🚀 TORPEDO FIRE product={product_id}, {len(accounts)} accounts ===")
    await _send_discord(f"🚀 **TORPEDO FIRE** product {product_id} — {len(accounts)} accounts")

    tasks = [torpedo_buy(acc, product_id) for acc in accounts]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    total = time.time() - t0
    ok = sum(1 for r in results if r is True)
    log.info(f"=== TORPEDO DONE: {ok}/{len(accounts)} in {total:.2f}s ===")

    status = "✅" if ok > 0 else "❌"
    await _send_discord(f"{status} **TORPEDO** product {product_id} | {ok}/{len(accounts)} | {total:.1f}s")
    return ok


async def daemon_loop(accounts):
    """Watch trigger file and fire when triggered."""
    log.info(f"[DAEMON] Watching {FIRE_FILE} for triggers ({len(accounts)} accounts ready)")
    while True:
        if FIRE_FILE.exists():
            try:
                product_id = FIRE_FILE.read_text().strip()
                FIRE_FILE.unlink()
                if product_id:
                    await fire(product_id, accounts)
            except Exception as e:
                log.error(f"[DAEMON] Error: {e}")
        await asyncio.sleep(0.5)


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="JC Torpedo — pure HTTP instant buy")
    parser.add_argument("--fire", "-f", help="Product ID to buy NOW (one-shot)")
    parser.add_argument("--test", action="store_true", help="Use test account (Marian)")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon (watch trigger file)")
    args = parser.parse_args()

    accounts = [TEST_ACCOUNT] if args.test else ACCOUNTS

    if args.fire:
        ok = await fire(args.fire, accounts)
        sys.exit(0 if ok > 0 else 1)
    elif args.daemon:
        await daemon_loop(accounts)
    else:
        print("Usage: --fire PRODUCT_ID | --daemon")
        print("  --fire 7437         Buy product 7437 now")
        print("  --fire 7437 --test  Buy on test account only")
        print("  --daemon            Run forever, watch /tmp/jc_torpedo_fire.txt")


if __name__ == "__main__":
    asyncio.run(main())
