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
            // Get ALL buttons and inputs on page
            const els = document.querySelectorAll('button, input[type="submit"], form');
            for (const el of els) {
                const text = (el.innerText || el.value || '').substring(0, 80);
                const cls = (el.className || '').substring(0, 150);
                const tag = el.tagName;
                const action = el.getAttribute('action') || '';
                const type = el.getAttribute('type') || '';
                const name = el.getAttribute('name') || '';
                const dataAttrs = Array.from(el.attributes).filter(a => a.name.startsWith('data-')).map(a => a.name + '=' + a.value.substring(0,50)).join(', ');
                results.push({tag, text: text.replace(/\\n/g,' ').trim(), cls, action, type, name, data: dataAttrs});
            }
            return JSON.stringify(results, null, 2);
        }""")
        print(info)
        await browser.close()

asyncio.run(main())
