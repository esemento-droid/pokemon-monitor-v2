#!/usr/bin/env python3
"""
Debug: Full flow using checkout() from tcgumisia_autobuy.
Takes screenshot AFTER submit on confirmation/tpay page.
Dumps page text to check if paczkomat is visible.
"""
import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from patchright.async_api import async_playwright
from tcgumisia_autobuy import login, clear_cart, add_to_cart, checkout, logout, TEST_ACCOUNT, BASE_URL, PROXY, PACZKOMAT, log

TEST_PRODUCT_URL = "https://tcgumisia.pl/pokemon-tcg-mega-moonlit-tin-mega-clefable-ex"

async def main():
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

        ok = await login(page, TEST_ACCOUNT["email"], TEST_ACCOUNT["password"])
        print(f"LOGIN: {'OK' if ok else 'FAILED'}")
        if not ok:
            await ctx.close()
            await browser.close()
            return

        await clear_cart(page)
        print("CART CLEARED")

        ok = await add_to_cart(page, TEST_PRODUCT_URL, qty=1)
        print(f"ATC: {'OK' if ok else 'FAILED'}")
        if not ok:
            await ctx.close()
            await browser.close()
            return

        # Run checkout with test_mode=True (will click Zamawiam)
        ok = await checkout(page, TEST_ACCOUNT, test_mode=True)
        print(f"CHECKOUT: {'OK' if ok else 'FAILED'}")
        print(f"URL after checkout: {page.url}")

        # Take screenshot of current page (tpay or confirmation)
        await page.screenshot(path="/opt/pokemon-monitor-v2/confirmation_screenshot.png")
        print("Screenshot: /opt/pokemon-monitor-v2/confirmation_screenshot.png")

        # Dump text
        body = await page.evaluate("() => document.body ? (document.body.innerText || '').substring(0, 1500) : ''")
        print(f"\n=== PAGE TEXT ===\n{body}")

        await logout(page)
        await ctx.close()
        await browser.close()

asyncio.run(main())
