#!/usr/bin/env python3
"""Debug: check if login actually works (session cookies, cart state)"""
import asyncio
from patchright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=['--no-sandbox', '--proxy-server=http://127.0.0.1:8888']
        )
        page = await browser.new_page()

        await page.goto('https://tcgumisia.pl', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(4)

        # Accept cookies
        await page.evaluate("""() => {
            const btn = document.querySelector('.js-accept-cookie-alert-1');
            if (btn) btn.click();
        }""")
        await asyncio.sleep(1)

        # Click Konto to open modal
        await page.evaluate("""() => {
            const btn = document.querySelector('button[data-aside-target="modal-aside-entry-form"]');
            if (btn) btn.click();
        }""")
        await asyncio.sleep(2)

        # Fill login form
        await page.evaluate("""() => {
            const form = document.querySelector('.js-login-form');
            if (!form) { console.log('NO FORM FOUND'); return; }
            const inputs = form.querySelectorAll('input');
            for (const inp of inputs) {
                if (inp.type === 'email' || inp.placeholder.toLowerCase().includes('e-mail')) {
                    inp.value = 't11008543@gmail.com';
                    inp.dispatchEvent(new Event('input', {bubbles:true}));
                    inp.dispatchEvent(new Event('change', {bubbles:true}));
                }
                if (inp.type === 'password' || inp.placeholder.toLowerCase().includes('has')) {
                    inp.value = 'mt!cSsphud4Zhnz';
                    inp.dispatchEvent(new Event('input', {bubbles:true}));
                    inp.dispatchEvent(new Event('change', {bubbles:true}));
                }
            }
        }""")
        await asyncio.sleep(1)

        # Click login button
        await page.evaluate("""() => {
            const btn = document.querySelector('.js-submit-login');
            if (btn) btn.click();
        }""")
        await asyncio.sleep(6)

        # Check cookies
        cookies = await page.context.cookies()
        print(f'URL after login: {page.url}')
        print(f'Total cookies: {len(cookies)}')
        for c in cookies:
            name = c['name'].lower()
            if 'session' in name or 'login' in name or 'auth' in name or 'customer' in name or 'user' in name or 'sell' in name:
                print(f'  RELEVANT: {c["name"]}={c["value"][:40]}...')

        # Check page text for login indicators
        text = await page.evaluate('() => document.body.innerText.substring(0, 300)')
        print(f'Page text: {text[:200]}')

        # Check if "Wyloguj" visible
        has_wyloguj = await page.evaluate("""() => {
            return document.body.innerText.toLowerCase().includes('wyloguj');
        }""")
        print(f'Has wyloguj: {has_wyloguj}')

        # Now navigate to /koszyk
        print('\\n=== Going to /koszyk ===')
        await page.goto('https://tcgumisia.pl/koszyk', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(4)
        cart_text = await page.evaluate('() => document.body.innerText.substring(0, 400)')
        print(f'Cart page: {cart_text[:300]}')

        await browser.close()

asyncio.run(main())
