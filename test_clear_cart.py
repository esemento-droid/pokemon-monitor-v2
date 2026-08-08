#!/usr/bin/env python3
"""Test: login, go to /pl/basket page, check what's there and try to clear"""
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
        print(f"LOGGED IN: {'wyloguj' in (await page.content()).lower()}")

        # Go directly to basket PAGE (not popup)
        await page.goto(f"{BASE_URL}/pl/basket", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        await page.evaluate("""
            document.querySelectorAll('.consents, .consents__mask, [class*=consent], .cookie-bar, h-portal-target[name="modals"], .consents-modal__footer, .modal__footer').forEach(el => el.remove());
            document.body.style.pointerEvents = 'auto';
        """)

        # What's on the basket page?
        body = await page.evaluate("() => document.body.innerText.substring(0, 600)")
        print(f"BASKET PAGE URL: {page.url}")
        print(f"BASKET BODY: {body[:400]}")

        # Look for remove/delete/Wyczysc/Usun buttons or links
        actions = await page.evaluate("""() => {
            const els = Array.from(document.querySelectorAll('button, a, span'));
            const relevant = els.filter(el => {
                const t = (el.innerText || '').toLowerCase();
                return t.includes('usuń') || t.includes('wyczyść') || t.includes('usuń') || 
                       t.includes('remove') || t.includes('delete') || t === 'x' || t === '×';
            });
            return relevant.map(el => ({tag: el.tagName, text: el.innerText.substring(0,30), cls: el.className.substring(0,40), href: el.href || ''}));
        }""")
        print(f"REMOVE ACTIONS: {actions}")

        # Also check for prodremove links (old Shoper)
        prodremove = await page.evaluate("""() => {
            const links = document.querySelectorAll('a.prodremove, a[href*="remove"], a[href*="delete"]');
            return Array.from(links).map(a => ({href: a.href, text: a.innerText.substring(0,20)}));
        }""")
        print(f"PRODREMOVE LINKS: {prodremove}")

        await browser.close()

asyncio.run(check())
