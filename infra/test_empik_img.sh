#!/bin/bash
cd /opt/pokemon-monitor-v2
DISPLAY=:99 ./venv/bin/python3 -c "
import asyncio
from shops.empik import scan_with_page
from patchright.async_api import async_playwright
async def test():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, args=['--no-sandbox','--disable-gpu','--proxy-server=http://127.0.0.1:8888','--disable-blink-features=AutomationControlled'])
        page = await browser.new_page()
        prods = await scan_with_page(page)
        await browser.close()
        print(f'Total: {len(prods)} products')
        for p in prods[:5]:
            print(f'{p[\"name\"][:50]} | img={p[\"image\"][:100]}')
asyncio.run(test())
" 2>&1 | tail -10
