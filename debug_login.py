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

        # Fill login form using Playwright native type (triggers keydown/keyup/keypress)
        email_input = page.locator('.js-login-form input[type="email"], .js-login-form input[placeholder*="E-mail"]').first
        pass_input = page.locator('.js-login-form input[type="password"]').first
        
        await email_input.click()
        await email_input.fill('t11008543@gmail.com')
        await asyncio.sleep(0.5)
        await pass_input.click()
        await pass_input.fill('mt!cSsphud4Zhnz')
        await asyncio.sleep(0.5)

        # Listen for network requests AND responses
        requests_log = []
        async def on_request(req):
            if req.method == 'POST' and 'login' in req.url.lower():
                post_data = req.post_data or 'NO POST DATA'
                requests_log.append(f'{req.method} {req.url} BODY: {post_data[:200]}')
        
        responses_log = []
        async def on_response(resp):
            if 'login' in resp.url.lower() or 'account' in resp.url.lower():
                try:
                    body = await resp.text()
                    responses_log.append(f'{resp.status} {resp.url} BODY: {body[:300]}')
                except:
                    responses_log.append(f'{resp.status} {resp.url} (no body)')
        
        page.on('request', lambda req: asyncio.ensure_future(on_request(req)))
        page.on('response', lambda resp: asyncio.ensure_future(on_response(resp)))

        # Click login button using Playwright click
        login_btn = page.locator('.js-submit-login')
        await login_btn.click()
        await asyncio.sleep(6)

        # Show network requests
        print(f'Requests: {len(requests_log)}')
        for r in requests_log:
            print(f'  {r}')
        print(f'Responses: {len(responses_log)}')
        for r in responses_log:
            print(f'  {r}')

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
