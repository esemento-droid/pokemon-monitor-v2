#!/usr/bin/env python3
import asyncio, sys, os
sys.path.insert(0, "/opt/pokemon-monitor-v2")
os.chdir("/opt/pokemon-monitor-v2")
os.environ.setdefault("DISPLAY", ":99")

async def test():
    from patchright.async_api import async_playwright
    print("Testing tcg-zielona.pl...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            proxy={"server": "http://127.0.0.1:8888"},
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        page = await browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        await page.goto("https://tcg-zielona.pl", wait_until="domcontentloaded", timeout=45000)
        for i in range(12):
            title = await page.title()
            content = await page.evaluate("() => document.body ? document.body.innerText.substring(0,150) : ''")
            print(f"  [{i}] title='{title[:40]}' body='{content[:80]}'")
            if "moment" not in title.lower() and "checking" not in title.lower() and "just" not in title.lower():
                break
            await asyncio.sleep(2)
        await asyncio.sleep(3)
        title = await page.title()
        url = page.url
        body = await page.evaluate("() => document.body ? document.body.innerText.substring(0, 500) : ''")
        print(f"\nFINAL: title='{title}'")
        print(f"URL: {url}")
        print(f"BODY: {body[:400]}")
        await browser.close()

asyncio.run(test())
