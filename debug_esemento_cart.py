#!/usr/bin/env python3
"""Debug: login esemento, clear cart, ATC, check price in cart"""
import asyncio
from patchright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--proxy-server=http://127.0.0.1:8888']
        )
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='pl-PL'
        )
        page = await ctx.new_page()

        # Login esemento
        await page.goto('https://tcgumisia.pl', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(4)
        try:
            await page.locator('.js-accept-cookie-alert-1').click(timeout=3000)
        except:
            pass
        await asyncio.sleep(1)
        await page.locator('button[data-aside-target="modal-aside-entry-form"]').click()
        await asyncio.sleep(2)
        e = page.locator('.js-login-form input[type="email"], .js-login-form input[placeholder*="E-mail"]').first
        pw = page.locator('.js-login-form input[type="password"]').first
        await e.click()
        await e.fill('esemento@gmail.com')
        await asyncio.sleep(0.5)
        await pw.click()
        await pw.fill('cR!9GW#x2wqJtGw')
        await asyncio.sleep(0.5)
        await page.locator('.js-submit-login').click()
        await asyncio.sleep(6)
        print('Login esemento done')

        # Clear cart
        await page.goto('https://tcgumisia.pl/koszyk', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(4)
        for i in range(5):
            empty = await page.evaluate("() => document.body.innerText.toLowerCase().includes('koszyk jest pusty')")
            if empty:
                break
            d = page.locator('.c-table-product__delete--desktop').first
            if await d.count() > 0:
                await d.click(force=True, timeout=5000)
                await asyncio.sleep(2)
                await page.goto('https://tcgumisia.pl/koszyk', wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(3)
            else:
                break
        print('Cart cleared')

        # ATC
        await page.goto('https://tcgumisia.pl/pokemon-tcg-ionos-bellibolt-ex-premium-collection', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(5)
        await page.locator('#product-card-add-to-card').click(timeout=5000)
        await asyncio.sleep(5)

        # Check cart
        await page.goto('https://tcgumisia.pl/koszyk', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(4)
        cart = await page.evaluate('() => document.body.innerText.substring(0, 400)')
        print('ESEMENTO CART:')
        print(cart[:300])

        await ctx.close()
        await browser.close()

asyncio.run(main())
