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
        await asyncio.sleep(10)  # Wait longer for JS render

        # First: just dump ALL text visible on page that mentions "dodaj" or "koszyk" or product area
        info = await page.evaluate("""() => {
            const results = [];
            
            // 1. Find element with text "Dodaj do koszyka" anywhere
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            while (walker.nextNode()) {
                const text = walker.currentNode.textContent.trim();
                if (text.toLowerCase().includes('dodaj do koszyka')) {
                    const parent = walker.currentNode.parentElement;
                    const rect = parent.getBoundingClientRect();
                    results.push({
                        type: 'TEXT_NODE',
                        text: text,
                        parentTag: parent.tagName,
                        parentCls: (parent.className || '').substring(0, 200),
                        parentId: parent.id,
                        visible: rect.width > 0 && rect.height > 0,
                        rect: `${Math.round(rect.x)}x${Math.round(rect.y)} ${Math.round(rect.width)}x${Math.round(rect.height)}`
                    });
                }
            }
            
            // 2. Also check page.url and title
            results.push({type: 'PAGE_INFO', url: location.href, title: document.title});
            
            // 3. Check main content area for product-related elements
            const mainContent = document.querySelector('.product, [class*="product"], main, .content, #content');
            if (mainContent) {
                results.push({type: 'MAIN_CONTENT', cls: (mainContent.className||'').substring(0,100), html_length: mainContent.innerHTML.length});
            }
            
            return JSON.stringify(results, null, 2);
        }""")
        print(info)
        await browser.close()

asyncio.run(main())
