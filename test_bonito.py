#!/usr/bin/env python3
import asyncio, sys, os, re
sys.path.insert(0, "/opt/pokemon-monitor-v2")
os.chdir("/opt/pokemon-monitor-v2")
os.environ.setdefault("DISPLAY", ":99")

async def test():
    from patchright.async_api import async_playwright
    print("Starting bonito URL debug...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            proxy={"server": "http://127.0.0.1:8888"},
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        page = await browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

        # First go to homepage to pass verification
        await page.goto("https://bonito.pl", wait_until="domcontentloaded", timeout=45000)
        for i in range(10):
            content = await page.evaluate("() => document.body ? document.body.innerText.substring(0,100) : ''")
            if "weryfikacja" not in content.lower() and "sprawdzanie" not in content.lower():
                break
            await asyncio.sleep(2)
        await asyncio.sleep(2)
        print(f"Homepage loaded, title: {await page.title()}")

        # Find search form in HTML
        html = await page.content()
        forms = re.findall(r'action="([^"]+)"', html)
        print(f"Forms found: {forms[:10]}")

        # Find search input
        search_inputs = re.findall(r'name="([^"]*)"[^>]*(?:search|szukaj)', html, re.I)
        print(f"Search-related inputs: {search_inputs[:10]}")

        # Try typing in search box
        search_box = await page.query_selector('input[type="search"], input[name*="search"], input[name*="szukaj"], input[name*="fraza"], input[placeholder*="szukaj"], input[placeholder*="Szukaj"]')
        if search_box:
            print("Found search box! Typing pokemon tcg...")
            await search_box.fill("pokemon tcg")
            await search_box.press("Enter")
            await asyncio.sleep(8)
            title = await page.title()
            url = page.url
            body = await page.evaluate("() => document.body ? document.body.innerText.substring(0, 300) : ''")
            print(f"After search: title='{title}' url='{url}'")
            print(f"Body: {body[:200]}")
        else:
            print("No search box found, trying URLs...")
            urls_to_try = [
                "https://bonito.pl/szukaj?q=pokemon+tcg",
                "https://bonito.pl/search?q=pokemon+tcg",
                "https://bonito.pl/wyszukiwarka?fraza=pokemon",
                "https://bonito.pl/k?q=pokemon+tcg",
                "https://bonito.pl/szukaj/pokemon+tcg",
            ]
            for url in urls_to_try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(3)
                t = await page.title()
                print(f"  {url} -> '{t[:50]}'")
                if "404" not in t and "nie istnieje" not in t.lower():
                    body = await page.evaluate("() => document.body.innerText.substring(0,200)")
                    print(f"  SUCCESS! Body: {body[:150]}")
                    break

        await browser.close()

asyncio.run(test())
