#!/usr/bin/env python3
"""Debug: dump all radio buttons, checkboxes and buttons on checkout Tab 1"""
import asyncio
from patchright.async_api import async_playwright

BASE_URL = "https://tcgumisia.pl"
PROXY = "http://127.0.0.1:8888"
PRODUCT_URL = "https://tcgumisia.pl/pokemon-tcg-ionos-bellibolt-ex-premium-collection"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=['--no-sandbox', f'--proxy-server={PROXY}']
        )
        page = await browser.new_page()

        # Login
        await page.goto(BASE_URL, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(4)
        try:
            await page.locator('.js-accept-cookie-alert-1').click(timeout=3000)
            await asyncio.sleep(1)
        except:
            pass
        await page.locator('button[data-aside-target="modal-aside-entry-form"]').click()
        await asyncio.sleep(2)
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
        print("Login done")

        # Clear cart
        await page.goto(f"{BASE_URL}/koszyk", wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(4)
        for i in range(5):
            empty = await page.evaluate("() => document.body.innerText.toLowerCase().includes('koszyk jest pusty')")
            if empty:
                break
            del_btn = page.locator('.c-table-product__delete--desktop').first
            if await del_btn.count() > 0:
                await del_btn.click(force=True, timeout=5000)
                await asyncio.sleep(2)
                await page.goto(f"{BASE_URL}/koszyk", wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(3)
            else:
                break
        print("Cart cleared")

        # ATC
        await page.goto(PRODUCT_URL, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(5)
        await page.locator('#product-card-add-to-card').click(timeout=5000)
        await asyncio.sleep(4)
        print("ATC done")

        # Go to checkout (koszyk)
        await page.goto(f"{BASE_URL}/koszyk", wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(5)

        # Dump ALL radios, checkboxes, selects, buttons on this page
        info = await page.evaluate("""() => {
            const results = [];
            
            // All radio buttons
            const radios = document.querySelectorAll('input[type="radio"]');
            for (const r of radios) {
                const label = r.closest('label') || r.parentElement;
                const labelText = label ? label.innerText.trim().substring(0, 80) : '';
                const name = r.name || '';
                const value = r.value || '';
                const checked = r.checked;
                const visible = r.offsetParent !== null;
                const cls = (r.className || '').substring(0, 100);
                const parentCls = (label ? label.className : '').substring(0, 100);
                results.push({type: 'RADIO', name, value, checked, visible, labelText, cls, parentCls});
            }
            
            // All checkboxes
            const checks = document.querySelectorAll('input[type="checkbox"]');
            for (const c of checks) {
                const label = c.closest('label') || c.parentElement;
                const labelText = label ? label.innerText.trim().substring(0, 80) : '';
                const name = c.name || '';
                const checked = c.checked;
                const visible = c.offsetParent !== null;
                results.push({type: 'CHECKBOX', name, checked, visible, labelText});
            }
            
            // Buttons with text
            const btns = document.querySelectorAll('button, a.c-button, input[type="submit"]');
            for (const b of btns) {
                const text = (b.innerText || b.value || '').trim().substring(0, 50);
                const visible = b.offsetParent !== null;
                const cls = (b.className || '').substring(0, 100);
                if (text && visible) {
                    results.push({type: 'BUTTON', text, cls});
                }
            }
            
            return JSON.stringify(results, null, 2);
        }""")
        print(info)

        await browser.close()

asyncio.run(main())
