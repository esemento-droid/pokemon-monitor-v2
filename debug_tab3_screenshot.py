#!/usr/bin/env python3
"""
Debug: Full flow — capture the INTERMEDIATE confirmation page
(between clicking 'Zamawiam' and tpay redirect).
That page shows paczkomat number.
"""
import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from patchright.async_api import async_playwright
from tcgumisia_autobuy import login, clear_cart, add_to_cart, logout, TEST_ACCOUNT, BASE_URL, PROXY, PACZKOMAT, log

TEST_PRODUCT_URL = "https://tcgumisia.pl/pokemon-tcg-mega-moonlit-tin-mega-clefable-ex"

async def run_checkout_capture(page, account):
    """Run checkout but capture intermediate page after submit."""
    await page.goto(f"{BASE_URL}/koszyk", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(4)

    # TAB 1: InPost
    await page.evaluate("""() => {
        const r = document.querySelector('input[name="shipment"][value="15"]');
        if (r) { const label = r.closest('label') || r.parentElement; if (label) label.click(); }
    }""")
    await asyncio.sleep(3)

    await page.locator(".inpost_search_point").click(force=True, timeout=5000)
    await asyncio.sleep(2)

    search = page.locator('input[name="easypack-search"]')
    await search.click(timeout=5000)
    await search.fill("")
    await search.type(PACZKOMAT, delay=100)
    await asyncio.sleep(3)

    await page.locator('.inpost-search__item-list.point').first.click(timeout=8000)
    await asyncio.sleep(3)

    # Click on map list
    await page.evaluate(f"""() => {{
        const links = document.querySelectorAll('a.list-point-link');
        for (const link of links) {{
            if ((link.textContent || '').toUpperCase().includes('{PACZKOMAT}')) {{
                link.click(); return;
            }}
        }}
    }}""")
    await asyncio.sleep(4)

    # Click "Wybierz" in detail popup
    await page.evaluate("""() => {
        const modal = document.querySelector('.widget-modal') || document;
        const allEls = modal.querySelectorAll('*');
        for (const el of allEls) {
            const text = (el.innerText || el.textContent || '').trim().toLowerCase();
            if (el.offsetHeight > 0 && el.childElementCount === 0 && text === 'wybierz') {
                el.click(); return;
            }
        }
    }""")
    await asyncio.sleep(3)

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

    # Dalej
    await page.locator('.js-cart-next').click(force=True, timeout=5000)
    await asyncio.sleep(4)

    # TAB 2: Regulamin + Dalej
    try:
        rules = page.locator('input[name="rules"]')
        if await rules.count() > 0 and not await rules.is_checked():
            await rules.click(force=True, timeout=5000)
    except:
        pass
    await asyncio.sleep(1)
    await page.locator('.js-cart-next').click(force=True, timeout=5000)
    await asyncio.sleep(4)

    # TAB 3: Click Zamawiam
    print("Clicking 'Zamawiam i płacę'...")
    await page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button, a, input[type="submit"]'));
        const submit = btns.find(el => {
            const text = (el.innerText || el.value || '').toLowerCase();
            return text.includes('zamawiam');
        });
        if (submit) submit.click();
    }""")

    # NOW: capture every page load for 15 seconds to catch intermediate page
    print("Waiting for intermediate confirmation page...")
    for i in range(15):
        await asyncio.sleep(1)
        url = page.url
        body = await page.evaluate("() => document.body ? (document.body.innerText || '').substring(0, 2000) : ''")
        
        # Check if we're on an intermediate page (not tpay, not koszyk)
        if "tpay" in url or "przelewy24" in url or "autopay" in url:
            print(f"\n[{i}s] Reached payment: {url}")
            break
        
        if "zamówienie" in body.lower() or "podsumowanie" in body.lower() or "potwierdzenie" in body.lower() or "paczkomat" in body.lower():
            print(f"\n[{i}s] CONFIRMATION PAGE FOUND!")
            print(f"URL: {url}")
            await page.screenshot(path="/opt/pokemon-monitor-v2/confirmation_page.png")
            print("Screenshot: confirmation_page.png")
            print(f"\n=== PAGE TEXT ===\n{body}")
            break
        
        if i == 0:
            # Take screenshot immediately after click
            await page.screenshot(path="/opt/pokemon-monitor-v2/after_submit_0s.png")
            print(f"[0s] URL: {url} (screenshot saved)")
        elif i == 2:
            await page.screenshot(path="/opt/pokemon-monitor-v2/after_submit_2s.png")
            print(f"[2s] URL: {url} (screenshot saved)")
            print(f"[2s] Text (first 500): {body[:500]}")

    print("\nDone.")


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
            await ctx.close(); await browser.close(); return

        await clear_cart(page)
        print("CART CLEARED")

        ok = await add_to_cart(page, TEST_PRODUCT_URL, qty=1)
        print(f"ATC: {'OK' if ok else 'FAILED'}")
        if not ok:
            await ctx.close(); await browser.close(); return

        await run_checkout_capture(page, TEST_ACCOUNT)

        await logout(page)
        await ctx.close()
        await browser.close()

asyncio.run(main())
