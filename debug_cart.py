#!/usr/bin/env python3
"""Debug: find remove button in cart on tcgumisia.pl"""
import asyncio
from patchright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=['--no-sandbox', '--proxy-server=http://127.0.0.1:8888']
        )
        page = await browser.new_page()

        # Login first
        await page.goto('https://tcgumisia.pl', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(4)
        await page.evaluate("""() => { const btn = document.querySelector('.js-accept-cookie-alert-1'); if (btn) btn.click(); }""")
        await asyncio.sleep(1)
        await page.evaluate("""() => { document.querySelector('button[data-aside-target="modal-aside-entry-form"]').click(); }""")
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

        # Go to cart
        await page.goto('https://tcgumisia.pl/koszyk', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(4)

        # Dump all clickable elements in cart area
        info = await page.evaluate("""() => {
            const results = [];
            // Find all elements that could be remove buttons
            const els = document.querySelectorAll('a, button, span, i, svg, [onclick], [class*="remove"], [class*="delete"], [class*="trash"], [title]');
            for (const el of els) {
                const text = (el.innerText || el.textContent || '').trim().substring(0, 50);
                const cls = (el.className || '').toString().substring(0, 150);
                const title = el.getAttribute('title') || '';
                const tag = el.tagName;
                const rect = el.getBoundingClientRect();
                // Only visible elements near product area (y > 200, y < 600)
                if (rect.width > 0 && rect.height > 0 && rect.y > 150 && rect.y < 600) {
                    if (cls.includes('remove') || cls.includes('delete') || cls.includes('trash') ||
                        cls.includes('close') || cls.includes('icon') || title.includes('Usuń') ||
                        text === 'Usuń' || text === 'X' || text === '×') {
                        results.push({tag, text, cls, title, rect: `${Math.round(rect.x)}x${Math.round(rect.y)} ${Math.round(rect.width)}x${Math.round(rect.height)}`});
                    }
                }
            }
            // Also dump cart content text
            const cartText = document.body.innerText.substring(0, 500);
            results.push({type: 'CART_TEXT', text: cartText.substring(0, 300)});
            return JSON.stringify(results, null, 2);
        }""")
        print(info)

        await browser.close()

asyncio.run(main())
