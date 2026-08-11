#!/usr/bin/env python3
"""
Tantis.pl Auto-Buy Bot - Full Patchright (CF bypass + fetch() inside browser).
All API calls done via page.evaluate(fetch()) to inherit CF clearance.

Usage:
    python3 tantis_autobuy.py <product_id> [product_id2 ...]
    python3 tantis_autobuy.py --test <product_id>   # dry-run (no actual order)
    python3 tantis_autobuy.py --all <product_id>    # all 4 accounts

Speed: ~12s CF + ~3s per account = ~25s total (4 accounts)
"""

import asyncio
import sys
import os
import re
import json
import logging
from datetime import datetime

# ============ CONFIG ============
ACCOUNTS = [
    {
        "email": "esemento@gmail.com",
        "password": "cR!9GW#x2wqJtGw",
        "name": "Tomasz Szczepaniak",
        "phone": "607183797",
        "pickup_point": "PAD04M",
    },
    {
        "email": "blackmat36@gmail.com",
        "password": "v2@pvDGt#ZuN3ui",
        "name": "Natalia Szczepaniak",
        "phone": "514635586",
        "pickup_point": "PAD04M",
    },
    {
        "email": "tjbtaniojuzbylo@gmail.com",
        "password": "P9XAfQE.SCwFq5i",
        "name": "Jagoda Kaczmarek",
        "phone": "535024946",
        "pickup_point": "PAD04M",
    },
    {
        "email": "y24015411@gmail.com",
        "password": "huw!e.twdCmv9@B",
        "name": "Miroslawa Szczepaniak",
        "phone": "603466903",
        "pickup_point": "PAD04M",
    },
]

DELIVERY_ID = 2       # InPost Paczkomat 24/7
PAYMENT_ID = 3        # Platnosc online (PayU)
QUANTITY = 2          # per product per account (fallback to 1 if limit)
BASE_URL = "https://tantis.pl"

# Logging
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tantis_autobuy.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("tantis_autobuy")

# --- Discord notifications ---
import aiohttp as _aiohttp_dc
from pathlib import Path as _Path_dc
WEBHOOK_FILE_TANTIS = _Path_dc(__file__).parent / "discord_webhook_tantis.txt"

async def send_discord_tantis(msg):
    try:
        if not WEBHOOK_FILE_TANTIS.exists():
            return
        url = WEBHOOK_FILE_TANTIS.read_text().strip()
        if not url:
            return
        async with _aiohttp_dc.ClientSession() as s:
            await s.post(url, json={"content": msg})
    except Exception as e:
        log.warning(f"Discord send failed: {e}")
# --- end Discord ---


# JavaScript helper that runs fetch() inside the browser context
JS_FETCH = """
async ([method, path, body, xsrf]) => {
    const headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
    };
    if (xsrf) headers['X-XSRF-TOKEN'] = decodeURIComponent(xsrf);
    
    const opts = { method, headers, credentials: 'same-origin' };
    if (body && method !== 'GET' && method !== 'DELETE') {
        opts.body = JSON.stringify(body);
    }
    
    const r = await fetch(path, opts);
    let text = '';
    try { text = await r.text(); } catch(e) {}
    const ct = r.headers.get('content-type') || '';
    return { status: r.status, text: text.substring(0, 2000), ct: ct };
}
"""

JS_FETCH_INERTIA = """
async ([method, path, body, xsrf]) => {
    const headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'X-Inertia': 'true',
        'X-Inertia-Version': '',
    };
    if (xsrf) headers['X-XSRF-TOKEN'] = decodeURIComponent(xsrf);
    
    const opts = { method, headers, credentials: 'same-origin', body: JSON.stringify(body) };
    const r = await fetch(path, opts);
    let text = '';
    try { text = await r.text(); } catch(e) {}
    return { status: r.status, text: text.substring(0, 3000) };
}
"""

JS_GET_XSRF = """
() => {
    const match = document.cookie.match(/XSRF-TOKEN=([^;]+)/);
    return match ? match[1] : null;
}
"""


async def run_bot(product_ids: list, dry_run: bool = False, num_accounts: int = 4):
    """Main bot: open browser, pass CF, then do checkout for each account."""
    from patchright.async_api import async_playwright
from bot_utils import wait_for_verification

    log.info(f"{'='*60}")
    log.info(f"TANTIS AUTO-BUY | Products: {product_ids} | DryRun: {dry_run} | Accounts: {num_accounts}")
    log.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"{'='*60}")

    accounts_to_use = ACCOUNTS[:min(num_accounts, len(ACCOUNTS))]
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            proxy={"server": "http://127.0.0.1:8888"},
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Step 0: Pass CF challenge
        log.info("[CF] Navigating to tantis.pl...")
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)

        for attempt in range(8):
            title = await page.title()
            if "moment" not in title.lower() and "checking" not in title.lower() and "just" not in title.lower():
                break
            log.info(f"[CF] Waiting... ({attempt+1}/8)")
            await asyncio.sleep(2)

        await asyncio.sleep(1)
        title = await page.title()
        log.info(f"[CF] Page title: {title}")

        # Verify we passed CF
        xsrf = await page.evaluate(JS_GET_XSRF)
        if not xsrf:
            log.error("[CF] FAILED - no XSRF cookie after CF")
            await browser.close()
            return [{"account": "ALL", "success": False, "error": "CF bypass failed"}]

        log.info(f"[CF] PASSED! XSRF: {xsrf[:30]}...")

        # Run for each account
        for i, account in enumerate(accounts_to_use):
            name = account["email"].split("@")[0]
            log.info(f"\n--- Account {i+1}/{len(accounts_to_use)}: {account['email']} ---")
            result = {"account": name, "success": False, "order_id": None, "error": None}

            try:
                # Get fresh XSRF
                xsrf = await page.evaluate(JS_GET_XSRF)

                # Login
                log.info(f"[{name}] Logging in...")
                r = await page.evaluate(JS_FETCH, ["POST", "/login", {
                    "user_email": account["email"],
                    "user_password": account["password"],
                }, xsrf])

                if r["status"] == 429:
                    log.warning(f"[{name}] Rate-limited, waiting 5s...")
                    await asyncio.sleep(5)
                    xsrf = await page.evaluate(JS_GET_XSRF)
                    r = await page.evaluate(JS_FETCH, ["POST", "/login", {
                        "user_email": account["email"],
                        "user_password": account["password"],
                    }, xsrf])

                if r["status"] != 200:
                    result["error"] = f"Login HTTP {r['status']}: {r['text'][:100]}"
                elif r["text"]:
                    try:
                        resp = json.loads(r["text"])
                        if "user_email" in resp or "user_password" in resp:
                            result["error"] = f"Login error: {r['text'][:150]}"
                    except json.JSONDecodeError:
                        pass  # HTML response = OK

                if not result["error"]:
                    log.info(f"[{name}] Login OK")
                    xsrf = await page.evaluate(JS_GET_XSRF)

                    # Clear cart
                    log.info(f"[{name}] Clearing cart...")
                    await page.evaluate(JS_FETCH, ["DELETE", "/front-api/v1/cart/clear", None, xsrf])
                    xsrf = await page.evaluate(JS_GET_XSRF)

                    # Add to cart (qty=2, fallback 1)
                    items = [{"productId": int(pid), "quantity": QUANTITY} for pid in product_ids]
                    log.info(f"[{name}] Adding {len(items)} items (qty={QUANTITY})...")
                    r = await page.evaluate(JS_FETCH, ["POST", "/front-api/v1/cart", {
                        "items": items, "addedFrom": 2
                    }, xsrf])

                    if r["status"] != 200 and QUANTITY > 1:
                        log.warning(f"[{name}] qty={QUANTITY} failed, trying qty=1...")
                        xsrf = await page.evaluate(JS_GET_XSRF)
                        items = [{"productId": int(pid), "quantity": 1} for pid in product_ids]
                        r = await page.evaluate(JS_FETCH, ["POST", "/front-api/v1/cart", {
                            "items": items, "addedFrom": 2
                        }, xsrf])

                    if r["status"] != 200:
                        result["error"] = f"Cart failed HTTP {r['status']}: {r['text'][:150]}"

                if not result["error"]:
                    log.info(f"[{name}] Cart OK")
                    xsrf = await page.evaluate(JS_GET_XSRF)

                    # Delivery
                    r = await page.evaluate(JS_FETCH, ["POST", "/front-api/v1/cart/delivery-save", {
                        "deliveryId": DELIVERY_ID
                    }, xsrf])
                    if r["status"] != 200:
                        result["error"] = f"Delivery failed HTTP {r['status']}"

                if not result["error"]:
                    log.info(f"[{name}] Delivery OK")
                    xsrf = await page.evaluate(JS_GET_XSRF)

                    # Payment
                    r = await page.evaluate(JS_FETCH, ["POST", "/front-api/v1/cart/payment-save", {
                        "paymentId": PAYMENT_ID
                    }, xsrf])
                    if r["status"] != 200:
                        log.warning(f"[{name}] Payment {PAYMENT_ID} failed ({r['status']}), trying paymentId=2...")
                        xsrf = await page.evaluate(JS_GET_XSRF)
                        r = await page.evaluate(JS_FETCH, ["POST", "/front-api/v1/cart/payment-save", {
                            "paymentId": 2
                        }, xsrf])
                    if r["status"] != 200:
                        result["error"] = f"Payment failed HTTP {r['status']}"

                if not result["error"]:
                    log.info(f"[{name}] Payment OK")
                    xsrf = await page.evaluate(JS_GET_XSRF)

                    # Place order
                    if dry_run:
                        log.info(f"[{name}] DRY RUN - order NOT placed")
                        result["success"] = True
                        result["order_id"] = "DRY_RUN"
                    else:
                        log.info(f"[{name}] PLACING ORDER...")
                        order_data = {
                            "deliveryId": DELIVERY_ID,
                            "paymentId": PAYMENT_ID,
                            "deliveryName": account["name"],
                            "deliveryPhone": account["phone"],
                            "deliveryEmail": account["email"],
                            "pickupPointId": account["pickup_point"],
                            "wantInvoice": 0,
                            "orderComment": "",
                        }

                        r = await page.evaluate(JS_FETCH_INERTIA, ["POST", "/v2/koszyk/zloz-zamowienie", order_data, xsrf])

                        if r["status"] == 200:
                            try:
                                resp = json.loads(r["text"])
                                component = resp.get("component", "")
                                url = resp.get("url", "")
                                props = resp.get("props", {})

                                if "CheckoutSummary" in component or "potwierdzenie" in url:
                                    order = props.get("checkoutSummaryProps", {}).get("order", {})
                                    oid = order.get("orderId") or order.get("orderIdWithShopPrefix", "")
                                    result["success"] = True
                                    result["order_id"] = oid
                                    log.info(f"[{name}] ORDER PLACED! ID: {oid}")
                                    await send_discord_tantis(f"\u2705 **{name}** - zamowienie {result.get('order_id','?')}!\nProdukty: {product_ids}")
                                elif "Cart" in component:
                                    result["error"] = "Redirected to cart"
                                elif "CheckoutPage" in component:
                                    errors = props.get("errors", {})
                                    result["error"] = f"Validation: {json.dumps(errors, ensure_ascii=False)[:200]}" if errors else "Checkout stuck"
                                else:
                                    result["error"] = f"Component: {component}"
                            except json.JSONDecodeError:
                                if "potwierdzenie" in r["text"].lower():
                                    result["success"] = True
                                    result["order_id"] = "OK (HTML)"
                                    log.info(f"[{name}] ORDER PLACED (HTML)")
                                    await send_discord_tantis(f"\u2705 **{name}** - zamowienie {result.get('order_id','?')}!\nProdukty: {product_ids}")
                                else:
                                    result["error"] = f"Non-JSON: {r['text'][:150]}"
                        elif r["status"] == 409:
                            r2 = await page.evaluate(JS_FETCH, ["POST", "/v2/koszyk/zloz-zamowienie", order_data, xsrf])
                            if r2["status"] == 200 and "potwierdzenie" in r2["text"].lower():
                                result["success"] = True
                                result["order_id"] = "OK (fallback)"
                            else:
                                result["error"] = f"409 + fallback {r2['status']}"
                        else:
                            result["error"] = f"Place order HTTP {r['status']}: {r['text'][:150]}"

            except Exception as e:
                result["error"] = f"{type(e).__name__}: {str(e)}"

            if not result["success"]:
                log.error(f"[{name}] FAILED: {result.get('error')}")

            results.append(result)

            # Logout and reload for next account
            try:
                xsrf = await page.evaluate(JS_GET_XSRF)
                await page.evaluate(JS_FETCH, ["POST", "/logout", None, xsrf])
                await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(1)
            except:
                pass

            if i < len(accounts_to_use) - 1:
                await asyncio.sleep(1)

        await browser.close()

    # Summary
    log.info(f"\n{'='*60}")
    success_count = sum(1 for r in results if r["success"])
    for r in results:
        s = "OK" if r["success"] else "FAIL"
        log.info(f"  [{s}] {r['account']}: order={r.get('order_id')} err={r.get('error')}")
    log.info(f"RESULT: {success_count}/{len(results)} orders placed")
    # Discord summary
    lines = [f"  {r['account']}: {'OK #'+str(r.get('order_id','')) if r['success'] else 'FAIL '+str(r.get('error',''))[:60]}" for r in results]
    await send_discord_tantis(f"\U0001f6d2 **Tantis AutoBuy** - {success_count}/{len(results)} kont OK\nProdukty: {product_ids}\n" + "\n".join(lines))
    log.info(f"{'='*60}")

    return results


def extract_product_id_from_url(url: str) -> str:
    match = re.search(r'-i(\d+)', url)
    if match:
        return match.group(1)
    match = re.search(r'i(\d+)', url)
    if match:
        return match.group(1)
    return None


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: python3 tantis_autobuy.py [--test] [--all] [--accounts N] <product_id> [...]")
        sys.exit(1)

    dry_run = "--test" in args
    if dry_run:
        args.remove("--test")

    use_all = "--all" in args
    if use_all:
        args.remove("--all")

    num_accounts = 4 if use_all else 4
    if "--accounts" in args:
        idx = args.index("--accounts")
        args.pop(idx)
        if idx < len(args):
            num_accounts = int(args.pop(idx))

    # Parse --qty (ignore it — bot uses hardcoded QUANTITY)
    if "--qty" in args:
        idx = args.index("--qty")
        args.pop(idx)
        if idx < len(args):
            args.pop(idx)  # remove the value too

    product_ids = []
    i = 0
    while i < len(args):
        if args[i] == "--url":
            i += 1
            if i < len(args):
                pid = extract_product_id_from_url(args[i])
                if pid:
                    product_ids.append(pid)
        else:
            product_ids.append(args[i])
        i += 1

    if not product_ids:
        log.error("No product IDs!")
        sys.exit(1)

    results = asyncio.run(run_bot(product_ids, dry_run, num_accounts))
    success = any(r["success"] for r in results)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
