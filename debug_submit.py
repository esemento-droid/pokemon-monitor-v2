#!/usr/bin/env python3
"""Debug: click Zamawiam via first PW locator"""
import asyncio
from patchright.async_api import async_playwright

BASE_URL = "https://www.kartexpol.pl"

async def check():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--no-sandbox","--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
        page = await ctx.new_page()

        # Login
        await page.goto(f"{BASE_URL}/pl/login", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        await page.evaluate("""
            document.querySelectorAll('.consents, .consents__mask, [class*=consent], .cookie-bar').forEach(el => el.remove());
            document.body.style.pointerEvents = 'auto';
        """)
        await page.evaluate("""() => {
            const m = document.querySelector('input[name="email"]');
            const p = document.querySelector('input[name="password"]');
            if (m) { m.focus(); m.value = 't11008543@gmail.com'; m.dispatchEvent(new Event('input',{bubbles:true})); }
            if (p) { p.focus(); p.value = 'mt!cSsphud4Zhnz'; p.dispatchEvent(new Event('input',{bubbles:true})); }
        }""")
        await asyncio.sleep(1)
        await page.evaluate("""() => { const btn = Array.from(document.querySelectorAll('button[type="submit"]')).find(b => b.innerText.includes('Zaloguj')); if (btn) btn.click(); }""")
        await asyncio.sleep(5)
        print(f"LOGGED IN: {'wyloguj' in (await page.content()).lower()}")

        # ATC
        await page.goto("https://www.kartexpol.pl/pl/p/Booster-Pokemon-Nihil-Zero/179", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        await page.evaluate("""() => { const btn = document.querySelector('.addtobasket'); if (btn) btn.click(); }""")
        await asyncio.sleep(3)

        # Checkout
        await page.goto(f"{BASE_URL}/pl/basket", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        await page.evaluate("""
            document.querySelectorAll('.consents, .consents__mask, [class*=consent], .cookie-bar').forEach(el => el.remove());
            document.body.style.pointerEvents = 'auto';
        """)
        await page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('a, button'));
            const btn = btns.find(b => b.innerText.includes('Dostawa') || b.innerText.toUpperCase().includes('ZAMAWIAM'));
            if (btn) btn.click();
        }""")
        await asyncio.sleep(6)
        print(f"CHECKOUT URL: {page.url}")

        # Select paczkomat
        await page.locator('input[name="nearest_pickup_point"]').first.click(force=True)
        await asyncio.sleep(2)
        print("PACZKOMAT: done")

        # Select BLIK
        await page.locator('input[name="basket_payment"][value="3:509"]').click(force=True)
        await asyncio.sleep(2)
        print("BLIK: done")

        # Check consent
        cb = page.locator('input[name="additional_2"]')
        if not await cb.is_checked():
            await cb.click(force=True)
        await asyncio.sleep(1)
        print("CONSENT: done")

        # Scroll to bottom and click submit via .first
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)
        
        submit = page.locator('button.btn_primary.btn_full-width').first
        print(f"SUBMIT BUTTON visible: {await submit.is_visible()}")
        await submit.scroll_into_view_if_needed()
        await asyncio.sleep(1)
        await submit.click(timeout=5000)
        print("SUBMIT: clicked via PW .first")
        
        await asyncio.sleep(15)
        print(f"URL AFTER: {page.url}")
        
        if "przelewy24" in page.url or "autopay" in page.url or "blik" in page.url:
            print("SUCCESS! Payment page reached!")
        else:
            body = await page.evaluate("() => document.body.innerText.substring(0, 300)")
            print(f"FAILED. Body: {body[:200]}")

        await browser.close()

asyncio.run(check())
