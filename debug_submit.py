#!/usr/bin/env python3
"""Debug: why Zamawiam i place button click doesnt redirect"""
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

        # Go to checkout via basket
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

        # Select paczkomat via PW locator click (not just JS)
        try:
            paczkomat = page.locator('input[name="nearest_pickup_point"]').first
            await paczkomat.click(force=True, timeout=5000)
            print("PACZKOMAT: clicked via PW locator")
        except Exception as e:
            print(f"PACZKOMAT PW click failed: {e}")
            await page.evaluate("""() => { const r = document.querySelector('input[name="nearest_pickup_point"]'); if(r) { r.checked=true; r.click(); } }""")
            print("PACZKOMAT: clicked via JS fallback")
        await asyncio.sleep(2)

        # Select BLIK via PW locator click
        try:
            blik = page.locator('input[name="basket_payment"][value="3:509"]')
            await blik.click(force=True, timeout=5000)
            print("BLIK: clicked via PW locator")
        except Exception as e:
            print(f"BLIK PW click failed: {e}")
            await page.evaluate("""() => { const r = document.querySelector('input[name="basket_payment"][value="3:509"]'); if(r) { r.checked=true; r.click(); } }""")
            print("BLIK: clicked via JS fallback")
        await asyncio.sleep(2)

        # Check consent
        await page.evaluate("""() => {
            ['additional_2','additional_3'].forEach(name => {
                const cb = document.querySelector('input[name="'+name+'"]');
                if (cb && !cb.checked) { cb.click(); }
            });
        }""")
        print("CHECKBOXES: clicked")
        await asyncio.sleep(2)

        # Check state before submit
        state = await page.evaluate("""() => {
            const pacz = document.querySelector('input[name="nearest_pickup_point"]:checked');
            const pay = document.querySelector('input[name="basket_payment"]:checked');
            const cb2 = document.querySelector('input[name="additional_2"]');
            const errors = document.querySelectorAll('.error, .alert, [class*="error"], [class*="alert"]');
            const errorTexts = Array.from(errors).map(e => e.innerText.substring(0,50)).filter(t => t.length > 0);
            return JSON.stringify({
                paczkomat: pacz?.value || 'NONE',
                payment: pay?.value || 'NONE', 
                consent_checked: cb2?.checked,
                errors: errorTexts
            });
        }""")
        print(f"STATE BEFORE SUBMIT: {state}")

        # Click Zamawiam via PW locator (force)
        try:
            submit = page.locator('button:has-text("Zamawiam i płacę")')
            await submit.click(force=True, timeout=5000)
            print("SUBMIT: clicked via PW locator")
        except Exception as e:
            print(f"SUBMIT PW failed: {e}, trying JS")
            await page.evaluate("""() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Zamawiam')); if(btn) btn.click(); }""")
            print("SUBMIT: clicked via JS")
        
        await asyncio.sleep(10)
        print(f"URL AFTER SUBMIT: {page.url}")
        
        # Check for errors on page
        errors = await page.evaluate("() => document.body.innerText.substring(0, 400)")
        print(f"BODY AFTER: {errors[:300]}")

        await browser.close()

asyncio.run(check())
