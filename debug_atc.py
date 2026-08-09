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
            // Search broadly - any element that might be an ATC button
            const els = document.querySelectorAll('*');
            for (const el of els) {
                const text = (el.innerText || el.textContent || '').trim();
                const cls = (el.className || '');
                // Look for anything with "dodaj" or "add" or "cart" in class/text
                if ((typeof cls === 'string' && (cls.includes('add') || cls.includes('cart') || cls.includes('product') || cls.includes('buy'))) ||
                    (text.toLowerCase().includes('dodaj do koszyka') && el.children.length === 0)) {
                    const tag = el.tagName;
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        results.push({
                            tag,
                            text: text.substring(0, 80),
                            cls: (typeof cls === 'string' ? cls : '').substring(0, 150),
                            rect: `${Math.round(rect.x)}x${Math.round(rect.y)} ${Math.round(rect.width)}x${Math.round(rect.height)}`,
                            data: Array.from(el.attributes || []).filter(a => a.name.startsWith('data-') || a.name === 'role').map(a => a.name + '=' + a.value.substring(0,50)).join(', ')
                        });
                    }
                }
            }
            return JSON.stringify(results, null, 2);
        }""")
        print(info)
        await browser.close()

asyncio.run(main())
