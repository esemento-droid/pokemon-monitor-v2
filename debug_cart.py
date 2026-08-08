#!/usr/bin/env python3
"""Debug: login, add to cart, then check basket state"""
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
        await asyncio.sleep(1)
        await page.evaluate("""() => {
            const m = document.querySelector('input[name="email"]');
            const p = document.querySelector('input[name="password"]');
            if (m) { m.focus(); m.value = 't11008543@gmail.com'; m.dispatchEvent(new Event('input',{bubbles:true})); m.dispatchEvent(new Event('change',{bubbles:true})); }
            if (p) { p.focus(); p.value = 'mt!cSsphud4Zhnz'; p.dispatchEvent(new Event('input',{bubbles:true})); p.dispatchEvent(new Event('change',{bubbles:true})); }
        }""")
        await asyncio.sleep(1)
        await page.evaluate("""() => {
            const btn = Array.from(document.querySelectorAll('button[type="submit"]')).find(b => b.innerText.includes('Zaloguj'));
            if (btn) btn.click();
        }""")
        await asyncio.sleep(5)
        content = await page.content()
        print(f"LOGGED IN: {'wyloguj' in content.lower()}")

        # Go to product page and ATC
        await page.goto("https://www.kartexpol.pl/pl/p/Booster-Pokemon-Nihil-Zero/179", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        await page.evaluate("""
            document.querySelectorAll('.consents, .consents__mask, [class*=consent], .cookie-bar').forEach(el => el.remove());
            document.body.style.pointerEvents = 'auto';
        """)

        # Check what ATC buttons exist
        btns = await page.evaluate("""() => {
            const all = Array.from(document.querySelectorAll('button, .addtobasket, [class*=addtobasket], [class*=koszyk]'));
            return all.map(b => ({tag:b.tagName, text:(b.innerText||'').substring(0,30), cls:b.className, disabled:b.disabled}));
        }""")
        print(f"ATC BUTTONS: {btns}")

        # Click ATC
        clicked = await page.evaluate("""() => {
            const btn = document.querySelector('.addtobasket') || 
                        document.querySelector('button.addtobasket') ||
                        document.querySelector('[class*="addtobasket"]');
            if (btn && !btn.disabled) { btn.click(); return 'clicked: ' + btn.className; }
            const fallback = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('koszyk') || b.innerText.includes('Koszyk'));
            if (fallback) { fallback.click(); return 'fallback: ' + fallback.innerText; }
            return 'NOT FOUND';
        }""")
        print(f"ATC CLICK: {clicked}")
        await asyncio.sleep(4)

        # Check current URL and page state
        print(f"URL AFTER ATC: {page.url}")

        # Navigate to basket
        await page.goto(f"{BASE_URL}/pl/basket", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        body = await page.evaluate("() => document.body.innerText.substring(0, 600)")
        has_zamawiam = "ZAMAWIAM" in body
        print(f"BASKET HAS ZAMAWIAM: {has_zamawiam}")
        print(f"BASKET BODY: {body[:400]}")

        await browser.close()

asyncio.run(check())
