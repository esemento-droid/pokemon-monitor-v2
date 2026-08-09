#!/usr/bin/env python3
"""
TCGumisia Full Flow Test — test account only
Runs the complete flow: login → ATC → checkout (InPost + Blik) on test account.
Uses WAW65N paczkomat. Will place a REAL order on test account!

Usage:
    DISPLAY=:99 timeout 300 venv/bin/python3 test_full_flow.py 2>&1 | curl -s -d @- https://paste.rs/
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tcgumisia_autobuy import (
    login, clear_cart, add_to_cart, checkout, logout,
    TEST_ACCOUNT, BASE_URL, PROXY, PACZKOMAT, log
)
from patchright.async_api import async_playwright


# Test product — pick any cheap available product on tcgumisia
# Update this URL to a product that's currently in stock!
TEST_PRODUCT_URL = "https://tcgumisia.pl/pokemon-tcg-scarlet-violet-prismatic-evolutions-booster-bundle-6-boosterow"


async def main():
    log.info("=" * 60)
    log.info("TCGumisia FULL FLOW TEST")
    log.info(f"Account: {TEST_ACCOUNT['email']} ({TEST_ACCOUNT['name']})")
    log.info(f"Paczkomat: {PACZKOMAT}")
    log.info(f"Product: {TEST_PRODUCT_URL}")
    log.info("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', f'--proxy-server={PROXY}']
        )

        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pl-PL"
        )
        page = await ctx.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
            Object.defineProperty(navigator, 'languages', {get: () => ['pl-PL', 'pl', 'en-US', 'en']});
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(param) {
                if (param === 37445) return 'Intel Inc.';
                if (param === 37446) return 'Intel Iris OpenGL Engine';
                return getParameter.call(this, param);
            };
        """)

        try:
            # Step 1: Login
            log.info("\n--- STEP 1: LOGIN ---")
            ok = await login(page, TEST_ACCOUNT["email"], TEST_ACCOUNT["password"])
            if not ok:
                log.error("❌ LOGIN FAILED — aborting")
                return
            log.info("✅ Login OK")

            # Step 2: Clear cart
            log.info("\n--- STEP 2: CLEAR CART ---")
            await clear_cart(page)
            log.info("✅ Cart cleared")

            # Step 3: Add to cart
            log.info("\n--- STEP 3: ADD TO CART ---")
            ok = await add_to_cart(page, TEST_PRODUCT_URL, qty=1)
            if not ok:
                log.error("❌ ATC FAILED — aborting")
                return
            log.info("✅ Product added to cart")

            # Step 4: Checkout (InPost + Blik)
            log.info("\n--- STEP 4: CHECKOUT ---")
            ok = await checkout(page, TEST_ACCOUNT, test_mode=True)
            if ok:
                log.info("\n✅✅✅ FULL FLOW SUCCESS — order placed on test account!")
                log.info(f"Final URL: {page.url}")
            else:
                log.error("\n❌ CHECKOUT FAILED")
                # Capture page state for debugging
                body = await page.evaluate("() => document.body.innerText.substring(0, 500)")
                log.error(f"Page URL: {page.url}")
                log.error(f"Page text: {body[:300]}")

                # Take screenshot for debug
                try:
                    await page.screenshot(path="/opt/pokemon-monitor-v2/debug_checkout_screenshot.png")
                    log.info("Screenshot saved: debug_checkout_screenshot.png")
                except Exception:
                    pass

        except Exception as e:
            log.error(f"❌ EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await logout(page)
            await ctx.close()
            await browser.close()

    log.info("\n--- TEST COMPLETE ---")


if __name__ == "__main__":
    asyncio.run(main())
