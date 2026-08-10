#!/usr/bin/env python3
"""
Test: Add product with qty=3 to cart on test account.
Does NOT checkout. Just shows cart contents for verification.
"""
import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from patchright.async_api import async_playwright
from tcgumisia_autobuy import login, clear_cart, add_to_cart, logout, TEST_ACCOUNT, BASE_URL, PROXY, log

TEST_PRODUCT_URL = "https://tcgumisia.pl/pokemon-tcg-mega-moonlit-tin-mega-clefable-ex"
TEST_QTY = 3

async def main():
    print(f"=== QTY TEST: {TEST_QTY} sztuk ===")
    print(f"Product: {TEST_PRODUCT_URL}")
    print(f"Account: {TEST_ACCOUNT['email']}")
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", f"--proxy-server={PROXY}"]
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pl-PL"
        )
        page = await ctx.new_page()

        # Login
        ok = await login(page, TEST_ACCOUNT["email"], TEST_ACCOUNT["password"])
        print(f"LOGIN: {'OK' if ok else 'FAILED'}")
        if not ok:
            await ctx.close()
            await browser.close()
            return

        # Clear cart
        await clear_cart(page)
        print("CART CLEARED")

        # Add to cart with qty=3
        print(f"\nAdding product with qty={TEST_QTY}...")
        ok = await add_to_cart(page, TEST_PRODUCT_URL, qty=TEST_QTY)
        print(f"ATC: {'OK' if ok else 'FAILED'}")

        if not ok:
            await logout(page)
            await ctx.close()
            await browser.close()
            return

        # Go to cart and dump contents
        await page.goto(f"{BASE_URL}/koszyk", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)

        # Get cart contents as text
        cart_text = await page.evaluate("""() => {
            const text = document.body ? (document.body.innerText || '') : '';
            return text.substring(0, 2000);
        }""")
        print(f"\n=== CART PAGE TEXT ===\n{cart_text}")

        # Specifically check qty input value
        qty_value = await page.evaluate("""() => {
            const inputs = document.querySelectorAll('input[type="number"]');
            const results = [];
            for (const inp of inputs) {
                if (inp.offsetParent !== null) {
                    results.push(inp.value);
                }
            }
            return results;
        }""")
        print(f"\n=== QTY INPUT VALUES IN CART: {qty_value} ===")

        # Cart total
        cart_val = await page.evaluate("""() => {
            const el = document.querySelector('.js-cart-value');
            return el ? el.innerText.trim() : '?';
        }""")
        print(f"CART TOTAL: {cart_val}")

        # NOT checking out - leave cart for user to verify
        print(f"\n=== DONE - Cart left for manual verification ===")
        print(f"Login: {TEST_ACCOUNT['email']} / {TEST_ACCOUNT['password']}")
        print(f"URL: {BASE_URL}/koszyk")

        await logout(page)
        await ctx.close()
        await browser.close()

asyncio.run(main())
