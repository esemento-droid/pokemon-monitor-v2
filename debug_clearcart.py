#!/usr/bin/env python3
"""Debug: test clear cart only"""
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

        # Open login modal
        await page.evaluate("""() => {
            document.querySelector('button[data-aside-target="modal-aside-entry-form"]').click();
        }""")
        await asyncio.sleep(2)

        # Fill and submit login
        email_input = page.locator('.js-login-form input[type="email"], .js-login-form input[placeholder*="E-mail"]').first
        pass_input = page.locator('.js-login-form input[type="password"]').first
        await email_input.click()
        await email_input.fill('t11008543@gmail.com')
        await asyncio.sleep(0.5)
        await pass_input.click()
        await pass_input.fill('mt!cSsphud4Zhnz')
        await asyncio.sleep(0.5)
        await page.locator('.js-submit-login').click()
        await asyncio.sleep(6)
        print('Login done, going to cart...')

        # Go to cart
        await page.goto('https://tcgumisia.pl/koszyk', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(4)

        # Remove items one by one
        for i in range(10):
            empty = await page.evaluate("""() => {
                return document.body.innerText.toLowerCase().includes('koszyk jest pusty');
            }""")
            if empty:
                print(f'Cart EMPTY after {i} removals')
                break

            # Click delete button via PW locator (desktop version)
            del_btn = page.locator('.js-cart-product-delete.c-table-product__delete--desktop').first
            try:
                count = await del_btn.count()
                if count == 0:
                    # Try any visible delete button
                    del_btn = page.locator('.js-cart-product-delete').first
                    count = await del_btn.count()
                    if count == 0:
                        print(f'No delete button found after {i} removals')
                        break
                await del_btn.click(force=True, timeout=5000)
            except Exception as e:
                print(f'Click failed: {e}')
                break

            print(f'Removed item {i+1}')
            await asyncio.sleep(2)
            await page.goto('https://tcgumisia.pl/koszyk', wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(3)

        # Final state
        cart = await page.evaluate('() => document.body.innerText.substring(0, 200)')
        print(f'Final cart: {cart[:150]}')
        await browser.close()

asyncio.run(main())
