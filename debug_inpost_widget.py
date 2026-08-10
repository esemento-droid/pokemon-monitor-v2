#!/usr/bin/env python3
"""Debug: dump InPost widget HTML after typing paczkomat code."""
import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from patchright.async_api import async_playwright
from tcgumisia_autobuy import login, TEST_ACCOUNT, BASE_URL, PROXY, PACZKOMAT, log

async def debug():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", f"--proxy-server={PROXY}"]
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
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

        await page.goto(f"{BASE_URL}/koszyk", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)

        # Click InPost radio
        await page.evaluate("""() => {
            const r = document.querySelector('input[name="shipment"][value="15"]');
            if (r) { const label = r.closest('label') || r.parentElement; if (label) label.click(); }
        }""")
        await asyncio.sleep(3)
        print("InPost radio clicked")

        # Click Wyszukaj
        try:
            await page.locator(".inpost_search_point").click(force=True, timeout=5000)
            print("Wyszukaj clicked")
        except Exception as e:
            print(f"Wyszukaj FAILED: {e}")
        await asyncio.sleep(2)

        # Type paczkomat
        search = page.locator('input[name="easypack-search"]')
        try:
            await search.click(timeout=5000)
            await search.fill("")
            await search.type(PACZKOMAT, delay=100)
            print(f"Typed: {PACZKOMAT}")
        except Exception as e:
            print(f"Type FAILED: {e}")
        await asyncio.sleep(3)

        # Get InPost widget HTML
        html = await page.evaluate("""() => {
            const widget = document.querySelector('.inpost-search') || document.querySelector('[class*="inpost"]');
            return widget ? widget.outerHTML.substring(0, 3000) : 'NO WIDGET FOUND';
        }""")
        print("\n=== INPOST WIDGET HTML ===")
        print(html)

        # Check dropdown items
        items = await page.evaluate("""() => {
            const items = document.querySelectorAll('.inpost-search__item-list.point');
            return Array.from(items).map(el => ({
                text: el.textContent.substring(0, 100).trim(),
                visible: el.offsetHeight > 0,
                classes: el.className,
                tag: el.tagName
            }));
        }""")
        print("\n=== DROPDOWN ITEMS (.inpost-search__item-list.point) ===")
        for item in items:
            print(f"  {item}")

        # Also check all elements with "WAW65N" text
        waw_els = await page.evaluate("""() => {
            const all = document.querySelectorAll('*');
            const found = [];
            for (const el of all) {
                if (el.childNodes.length <= 3 && (el.textContent || '').includes('WAW65N')) {
                    found.push({tag: el.tagName, classes: el.className, text: el.textContent.substring(0,80).trim()});
                }
            }
            return found.slice(0, 15);
        }""")
        print("\n=== ELEMENTS WITH WAW65N TEXT ===")
        for el in waw_els:
            print(f"  {el}")

        await ctx.close()
        await browser.close()

asyncio.run(debug())
