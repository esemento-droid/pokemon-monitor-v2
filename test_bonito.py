#!/usr/bin/env python3
import asyncio, sys, os
sys.path.insert(0, "/opt/pokemon-monitor-v2")
os.chdir("/opt/pokemon-monitor-v2")
os.environ.setdefault("DISPLAY", ":99")

async def test():
    from patchright.async_api import async_playwright
    print("Starting bonito debug...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            proxy={"server": "http://127.0.0.1:8888"},
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        page = await browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        await page.goto("https://bonito.pl/szukaj?fraza=pokemon+tcg", wait_until="domcontentloaded", timeout=45000)
        print("Page loaded, waiting for verification...")
        for i in range(15):
            content = await page.evaluate("() => document.body ? document.body.innerText.substring(0, 300) : ''")
            title = await page.title()
            print(f"  [{i}] title='{title[:40]}' content='{content[:80]}'")
            if "weryfikacja" not in content.lower() and "sprawdzanie" not in content.lower():
                break
            await asyncio.sleep(2)
        await asyncio.sleep(3)
        title = await page.title()
        url = page.url
        html = await page.content()
        print(f"\nFINAL: title='{title}' url='{url}' html_len={len(html)}")
        print(f"First 500 chars of body text:")
        body = await page.evaluate("() => document.body ? document.body.innerText.substring(0, 500) : ''")
        print(body)
        await browser.close()

asyncio.run(test())
