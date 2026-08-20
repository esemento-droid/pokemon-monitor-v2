#!/usr/bin/env python3
"""Test: can we ATC an OOS product via Sky-Shop API?"""
import asyncio
import aiohttp
import json
import re
import time

SHOP = "https://japancollectibles.shop"
PROXY = "http://127.0.0.1:8888"
EMAIL = "t11008543@gmail.com"
PASS = "mt!cSsphud4Zhnz"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# 9419 = Pakiet 30th (was available 5s, likely OOS now)
# 7437 = Mini Tin (available, control test)
TEST_PRODUCTS = [9419, 7437]


async def main():
    t0 = time.time()
    jar = aiohttp.CookieJar(unsafe=True)
    conn = aiohttp.TCPConnector(ssl=False)

    async with aiohttp.ClientSession(connector=conn, cookie_jar=jar, headers={"User-Agent": UA}) as s:
        # Login
        r = await s.get(f"{SHOP}/login", proxy=PROXY, timeout=aiohttp.ClientTimeout(total=8))
        html = await r.text()
        csrf = re.search(r'name="csrf_token"\s*value="([^"]+)"', html)
        csrf = csrf.group(1) if csrf else ""
        await s.post(f"{SHOP}/login", data={"email": EMAIL, "password": PASS, "autologin": "1", "csrf_token": csrf, "submit": "submit"}, proxy=PROXY, timeout=aiohttp.ClientTimeout(total=8), allow_redirects=True)
        print(f"Login OK ({time.time()-t0:.1f}s)")

        # Get cart
        r = await s.get(f"{SHOP}/proxy_public_api?endpoint=/sky2/api-public/carts/bulk/latest", proxy=PROXY, timeout=aiohttp.ClientTimeout(total=5))
        cart = await r.json()
        cart_id = cart.get("cart", {}).get("id", "")
        print(f"Cart: {cart_id[:12]}...")

        # Clear cart
        items = cart.get("cart", {}).get("items", [])
        for item in items:
            iid = item.get("id", "")
            if iid:
                await s.delete(f"{SHOP}/proxy_public_api?endpoint=/sky2/api-public/carts/{cart_id}/items/{iid}", headers={"Accept": "application/json", "currency": "PLN", "lang": "pl"}, proxy=PROXY, timeout=aiohttp.ClientTimeout(total=3))
        if items:
            print(f"Cleared {len(items)} items")

        # Test ATC on each product
        for pid in TEST_PRODUCTS:
            print(f"\n=== ATC test: product {pid} ===")
            r = await s.post(
                f"{SHOP}/proxy_public_api?endpoint=/sky2/api-public/carts/{cart_id}/items",
                json={"productId": pid, "quantity": 1, "parameters": []},
                headers={"Content-Type": "application/json;charset=UTF-8", "Accept": "application/json", "currency": "PLN", "lang": "pl", "Origin": SHOP},
                proxy=PROXY, timeout=aiohttp.ClientTimeout(total=5),
            )
            status = r.status
            text = await r.text()
            print(f"  HTTP {status}")
            try:
                data = json.loads(text)
                added = data.get("addedCartItem")
                if added:
                    price = added.get("priceSummary", {}).get("final", {}).get("grossDisplay", "?")
                    print(f"  ✅ ADDED! price={price}")
                    # Check cart state
                    r2 = await s.get(f"{SHOP}/proxy_public_api?endpoint=/sky2/api-public/carts/bulk/{cart_id}", proxy=PROXY, timeout=aiohttp.ClientTimeout(total=3))
                    c2 = await r2.json()
                    cart_items = c2.get("cart", {}).get("items", [])
                    can_buy = c2.get("cart", {}).get("canBuy", False)
                    print(f"  Cart: {len(cart_items)} items, canBuy={can_buy}")
                    # Remove for next test
                    for it in cart_items:
                        await s.delete(f"{SHOP}/proxy_public_api?endpoint=/sky2/api-public/carts/{cart_id}/items/{it['id']}", headers={"Accept": "application/json", "currency": "PLN", "lang": "pl"}, proxy=PROXY, timeout=aiohttp.ClientTimeout(total=3))
                else:
                    # Check for error info
                    errors = data.get("errors", data.get("error", data.get("message", "")))
                    violations = data.get("violations", [])
                    print(f"  ❌ NOT ADDED")
                    print(f"  Response keys: {list(data.keys())}")
                    print(f"  Errors: {errors}")
                    print(f"  Violations: {violations}")
                    print(f"  Full: {text[:400]}")
            except Exception as e:
                print(f"  Parse error: {e}")
                print(f"  Raw: {text[:400]}")

        print(f"\nDone ({time.time()-t0:.1f}s)")


asyncio.run(main())
