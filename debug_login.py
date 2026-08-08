#!/usr/bin/env python3
import asyncio
from patchright.async_api import async_playwright

async def check():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--no-sandbox","--disable-blink-features=AutomationControlled"])
        page = await browser.new_page()
        await page.goto("https://www.kartexpol.pl/pl/login", wait_until="domcontentloaded")
        await asyncio.sleep(5)
        info = await page.evaluate("""() => {
            const inputs = Array.from(document.querySelectorAll("input")).map(i => ({name:i.name, id:i.id, type:i.type}));
            const forms = Array.from(document.querySelectorAll("form")).map(f => ({action:f.action}));
            const body = document.body.innerText.substring(0,800);
            return JSON.stringify({inputs, forms, body}, null, 2);
        }""")
        print(info)
        await browser.close()

asyncio.run(check())
