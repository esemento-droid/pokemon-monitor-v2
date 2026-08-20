#!/bin/bash
cd /opt/pokemon-monitor-v2
DISPLAY=:99 ./venv/bin/python3 -c "
import asyncio
from patchright.async_api import async_playwright
async def test():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, args=['--no-sandbox','--disable-gpu','--proxy-server=http://127.0.0.1:8888','--disable-blink-features=AutomationControlled'])
        page = await browser.new_page()
        await page.goto('https://www.empik.com/szukaj/produkt?q=pokemon+tcg&searchCategory=all&sort=publishDesc', wait_until='domcontentloaded', timeout=45000)
        await asyncio.sleep(15)
        # Get raw HTML of first 3 product items - all img attributes
        data = await page.evaluate('''() => {
            const items = document.querySelectorAll('.search-list-item');
            const result = [];
            for (let i = 0; i < Math.min(3, items.length); i++) {
                const item = items[i];
                const imgs = item.querySelectorAll('img');
                const imgData = [];
                for (const img of imgs) {
                    imgData.push({
                        src: img.src || '',
                        dataSrc: img.getAttribute('data-src') || '',
                        dataLazy: img.getAttribute('data-lazy-img') || '',
                        dataOriginal: img.getAttribute('data-original') || '',
                        srcset: img.getAttribute('srcset') || '',
                        className: img.className || '',
                        alt: img.alt || '',
                        outerHTML: img.outerHTML.substring(0, 300)
                    });
                }
                const title = item.querySelector('h2.product-title');
                result.push({name: title ? title.textContent.trim().substring(0, 50) : '?', imgs: imgData});
            }
            return JSON.stringify(result, null, 2);
        }''')
        print(data)
        await browser.close()
asyncio.run(test())
" 2>&1 | tail -80
