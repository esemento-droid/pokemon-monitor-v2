#!/usr/bin/env python3
"""Debug: find ATC button element on tcgumisia product page"""
import asyncio
from patchright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=['--no-sandbox', '--proxy-server=http://127.0.0.1:8888']
        )
        page = await browser.new_page()
        await page.goto('https://tcgumisia.pl/pokemon-tcg-poke-ball-tin-2025', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(5)

        info = await page.evaluate("""() => {
            const results = [];
            const els = document.querySelectorAll('button, a, input[type="submit"], [onclick], form');
            for (const el of els) {
                const text = (el.innerText || el.value || '').toLowerCase().substring(0, 60);
                const href = el.getAttribute('href') || '';
                const onclick = el.getAttribute('onclick') || '';
                const cls = (el.className || '').substring(0, 120);
                const tag = el.tagName;
                const action = el.getAttribute('action') || '';
                const method = el.getAttribute('method') || '';
                if (text.includes('koszyk') || text.includes('dodaj') || 
                    cls.includes('cart') || cls.includes('basket') || cls.includes('add') ||
                    action.includes('koszyk') || action.includes('cart') ||
                    href.includes('koszyk') || href.includes('cart')) {
                    results.push({tag, text, href, onclick: onclick.substring(0,150), cls, id: el.id, action, method});
                }
            }
            return JSON.stringify(results, null, 2);
        }""")
        print(info)
        await browser.close()

asyncio.run(main())
