#!/usr/bin/env python3
"""Debug: what happens AFTER clicking paczkomat on map list."""
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

        # Go to cart
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
        await search.click(timeout=5000)
        await search.fill("")
        await search.type(PACZKOMAT, delay=100)
        print(f"Typed: {PACZKOMAT}")
        await asyncio.sleep(3)

        # Click autocomplete dropdown
        try:
            await page.locator('.inpost-search__item-list.point').first.click(timeout=5000)
            print("Autocomplete dropdown clicked")
        except Exception as e:
            print(f"Autocomplete click FAILED: {e}")
        await asyncio.sleep(3)

        # Click map list item
        map_clicked = await page.evaluate(f"""() => {{
            const links = document.querySelectorAll('a.list-point-link');
            for (const link of links) {{
                if ((link.textContent || '').toUpperCase().includes('{PACZKOMAT}')) {{
                    link.click();
                    return 'clicked: ' + link.textContent.substring(0, 50);
                }}
            }}
            return 'NOT FOUND';
        }}""")
        print(f"Map list click: {map_clicked}")
        await asyncio.sleep(5)

        # NOW check what appeared
        print("\n=== AFTER MAP LIST CLICK (5s wait) ===")

        # Check inpost_code
        code = await page.evaluate("() => { const i = document.querySelector('#inpost_code'); return i ? i.value : 'N/A'; }")
        print(f"#inpost_code: '{code}'")

        # Check inpost_chosen
        chosen = await page.evaluate("() => { const s = document.querySelector('.inpost_chosen'); return s ? s.textContent.trim() : 'N/A'; }")
        print(f".inpost_chosen: '{chosen}'")

        # Check for any detail popup or confirm button in widget
        popup = await page.evaluate("""() => {
            const modal = document.querySelector('.widget-modal') || document.querySelector('.easypack-widget');
            if (!modal) return 'NO MODAL';
            // Look for detail/info panels that appeared
            const details = modal.querySelectorAll('[class*="detail"], [class*="info"], [class*="popup"], [class*="selected"]');
            const result = [];
            for (const d of details) {
                if (d.offsetHeight > 0) {
                    result.push({classes: d.className.substring(0, 60), text: d.textContent.substring(0, 100).trim()});
                }
            }
            return result.length > 0 ? result : 'NO DETAIL PANELS VISIBLE';
        }""")
        print(f"Detail panels: {popup}")

        # All visible buttons/links in modal
        buttons = await page.evaluate("""() => {
            const modal = document.querySelector('.widget-modal') || document.querySelector('.easypack-widget');
            if (!modal) return ['NO MODAL'];
            const btns = modal.querySelectorAll('button, a[href], div[role="button"], [class*="btn"], [class*="button"], [class*="confirm"], [class*="select"]');
            return Array.from(btns).filter(b => b.offsetHeight > 0).map(b => ({
                tag: b.tagName,
                classes: (b.className || '').substring(0, 80),
                text: (b.innerText || b.textContent || '').substring(0, 60).trim()
            })).slice(0, 20);
        }""")
        print("\n=== VISIBLE BUTTONS/LINKS IN MODAL ===")
        for btn in buttons:
            print(f"  {btn}")

        # Full modal innerText
        modal_text = await page.evaluate("""() => {
            const modal = document.querySelector('.widget-modal');
            return modal ? modal.innerText.substring(0, 600) : 'NO MODAL';
        }""")
        print(f"\n=== MODAL INNERTEXT ===\n{modal_text}")

        await ctx.close()
        await browser.close()

asyncio.run(debug())
