#!/usr/bin/env python3
"""Test: login and clear cart only"""
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
            document.querySelectorAll('.consents, .consents__mask, [class*=consent], .cookie-bar, h-portal-target[name="modals"], .consents-modal__footer, .modal__footer').forEach(el => el.remove());
            document.body.style.pointerEvents = 'auto';
        """)
        await page.evaluate("""() => {
            const m = document.querySelector('input[name="email"]');
            const p = document.querySelector('input[name="password"]');
            if (m) { m.focus(); m.value = 't11008543@gmail.com'; m.dispatchEvent(new Event('input',{bubbles:true})); m.dispatchEvent(new Event('change',{bubbles:true})); }
            if (p) { p.focus(); p.value = 'mt!cSsphud4Zhnz'; p.dispatchEvent(new Event('input',{bubbles:true})); p.dispatchEvent(new Event('change',{bubbles:true})); }
        }""")
        await asyncio.sleep(1)
        await page.evaluate("""() => { const btn = Array.from(document.querySelectorAll('button[type="submit"]')).find(b => b.innerText.includes('Zaloguj')); if (btn) btn.click(); }""")
        await asyncio.sleep(5)
        logged = 'wyloguj' in (await page.content()).lower()
        print(f"LOGGED IN: {logged}")
        if not logged:
            print("LOGIN FAILED")
            await browser.close()
            return

        # Now clear cart
        print("Attempting to clear cart...")
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        await page.evaluate("""
            document.querySelectorAll('.consents, .consents__mask, [class*=consent], .cookie-bar, h-portal-target[name="modals"], .consents-modal__footer, .modal__footer').forEach(el => el.remove());
            document.body.style.pointerEvents = 'auto';
        """)

        # Click cart icon
        try:
            cart_icon = page.locator('a[href*="basket"], [class*="cart-icon"], [class*="basket-icon"]').first
            await cart_icon.click(force=True, timeout=5000)
            print("Clicked cart icon via PW")
        except Exception as e:
            print(f"Cart icon PW failed: {e}")
            await page.evaluate("""() => {
                const cart = document.querySelector('a[href*="basket"]');
                if (cart) cart.click();
            }""")
            print("Clicked cart icon via JS")
        await asyncio.sleep(3)

        # Check what's visible now
        popup_text = await page.evaluate("() => document.body.innerText.substring(0, 500)")
        print(f"AFTER CART CLICK: {popup_text[:200]}")

        # Look for "Wyczyść" 
        wyczysz = await page.evaluate("""() => {
            const els = Array.from(document.querySelectorAll('button, a, span, div'));
            const found = els.filter(el => el.innerText.trim() === 'Wyczyść' || el.innerText.trim() === 'Wyczysc');
            return found.map(f => ({tag: f.tagName, cls: f.className.substring(0,40), visible: f.offsetParent !== null}));
        }""")
        print(f"WYCZYSZ ELEMENTS: {wyczysz}")

        # Click "Wyczyść"
        try:
            clear_btn = page.locator('text=Wyczyść').first
            await clear_btn.click(force=True, timeout=5000)
            print("Clicked Wyczyść via PW")
        except Exception as e:
            print(f"Wyczyść PW failed: {e}")
            await page.evaluate("""() => {
                const btn = Array.from(document.querySelectorAll('*')).find(el => el.innerText.trim() === 'Wyczyść');
                if (btn) btn.click();
            }""")
            print("Clicked Wyczyść via JS")
        await asyncio.sleep(3)

        # Look for "Usuń wszystkie produkty" modal
        modal_text = await page.evaluate("() => document.body.innerText.substring(0, 300)")
        print(f"AFTER WYCZYSZ: {modal_text[:200]}")

        # Click "Usuń wszystkie produkty"
        try:
            remove_btn = page.locator('button:has-text("Usuń wszystkie produkty")').first
            await remove_btn.click(force=True, timeout=5000)
            print("Clicked 'Usuń wszystkie produkty' via PW")
        except Exception as e:
            print(f"Usuń PW failed: {e}")
            await page.evaluate("""() => {
                const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Usuń wszystkie'));
                if (btn) btn.click();
            }""")
            print("Clicked 'Usuń wszystkie' via JS")
        await asyncio.sleep(3)

        # Check result
        result = await page.evaluate("""() => {
            const text = document.body.innerText;
            if (text.includes('koszyk jest pusty') || text.includes('0,00')) return 'EMPTY';
            return 'NOT EMPTY: ' + text.substring(0, 100);
        }""")
        print(f"CART STATUS: {result}")

        await browser.close()

asyncio.run(check())
