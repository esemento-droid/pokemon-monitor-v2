#!/usr/bin/env python3
"""Debug: run flow up to Tab 3 and take screenshot + dump summary text. Does NOT submit order."""
import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from patchright.async_api import async_playwright
from tcgumisia_autobuy import login, clear_cart, add_to_cart, checkout, TEST_ACCOUNT, BASE_URL, PROXY, PACZKOMAT, log

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

        # Login
        ok = await login(page, TEST_ACCOUNT["email"], TEST_ACCOUNT["password"])
        if not ok:
            print("LOGIN FAILED")
            await ctx.close()
            await browser.close()
            return
        print("LOGIN OK")

        # Clear cart
        await clear_cart(page)
        print("CART CLEARED")

        # ATC
        ok = await add_to_cart(page, TEST_PRODUCT_URL, qty=1)
        if not ok:
            print("ATC FAILED")
            await ctx.close()
            await browser.close()
            return
        print("ATC OK")

        # Go to cart
        await page.goto(f"{BASE_URL}/koszyk", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)

        # === TAB 1: InPost + Blik + Dalej ===
        # InPost radio
        await page.evaluate("""() => {
            const r = document.querySelector('input[name="shipment"][value="15"]');
            if (r) { const label = r.closest('label') || r.parentElement; if (label) label.click(); }
        }""")
        await asyncio.sleep(3)

        # Wyszukaj
        await page.locator(".inpost_search_point").click(force=True, timeout=5000)
        await asyncio.sleep(2)

        # Type paczkomat
        search = page.locator('input[name="easypack-search"]')
        await search.click(timeout=5000)
        await search.fill("")
        await search.type(PACZKOMAT, delay=100)
        await asyncio.sleep(3)

        # Click autocomplete dropdown
        await page.locator('.inpost-search__item-list.point').first.click(timeout=8000)
        await asyncio.sleep(3)

        # Click map list
        await page.evaluate(f"""() => {{
            const links = document.querySelectorAll('a.list-point-link');
            for (const link of links) {{
                if ((link.textContent || '').toUpperCase().includes('{PACZKOMAT}')) {{
                    link.click();
                    return;
                }}
            }}
        }}""")
        await asyncio.sleep(4)

        # Check inpost_code
        code = await page.evaluate("() => { const i = document.querySelector('#inpost_code'); return i ? i.value : ''; }")
        print(f"#inpost_code = '{code}'")

        # Close modal
        await page.evaluate("""() => {
            const allEls = document.querySelectorAll('.widget-modal *');
            for (const el of allEls) {
                if ((el.textContent || '').trim() === '✕' && el.offsetHeight > 0) { el.click(); return; }
            }
        }""")
        await asyncio.sleep(2)

        # Blik
        try:
            await page.locator('input[name="payment"][value="25"]').click(force=True, timeout=5000)
        except:
            await page.evaluate("""() => {
                const r = document.querySelector('input[name="payment"][value="25"]');
                if (r) { const l = r.closest('label') || r.parentElement; if (l) l.click(); }
            }""")
        await asyncio.sleep(2)

        # Dalej Tab1->Tab2
        await page.locator('.js-cart-next').click(force=True, timeout=5000)
        await asyncio.sleep(4)

        # === TAB 2: Regulamin + Dalej ===
        # Regulamin
        try:
            rules = page.locator('input[name="rules"]')
            if await rules.count() > 0 and not await rules.is_checked():
                await rules.click(force=True, timeout=5000)
        except:
            await page.evaluate("""() => { const c = document.querySelector('input[name="rules"]'); if (c && !c.checked) { c.checked = true; c.dispatchEvent(new Event('change', {bubbles:true})); } }""")
        await asyncio.sleep(1)

        # Dalej Tab2->Tab3
        await page.locator('.js-cart-next').click(force=True, timeout=5000)
        await asyncio.sleep(4)

        # === TAB 3: SCREENSHOT ===
        print("\n=== TAB 3 SUMMARY ===")
        body_text = await page.evaluate("() => document.body ? (document.body.innerText || '').substring(0, 1500) : ''")
        print(body_text)

        # Screenshot
        await page.screenshot(path="/opt/pokemon-monitor-v2/tab3_screenshot.png")
        print("\nScreenshot saved: /opt/pokemon-monitor-v2/tab3_screenshot.png")

        # Do NOT submit
        print("\n[NOT SUBMITTING - debug only]")

        await ctx.close()
        await browser.close()

asyncio.run(main())
