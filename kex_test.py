import asyncio, json
from playwright.async_api import async_playwright
async def t():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--no-sandbox","--disable-blink-features=AutomationControlled"])
        page = await browser.new_page()
        captured = []
        async def on_req(route):
            req = route.request
            if "/api/basket/" in req.url and req.method in ("PUT","POST"):
                captured.append({"m":req.method,"url":req.url.split("/api/")[-1],"body":req.post_data or ""})
            await route.continue_()
        await page.route("**/api/basket/**", on_req)
        await page.goto("https://www.kartexpol.pl/pl/p/Pokemon-TCG-Mega-Symphonia-Booster-Box-m/158", wait_until="networkidle")
        await asyncio.sleep(3)
        await page.locator('button:has-text("Dodaj do koszyka")').first.click(force=True, timeout=5000)
        await asyncio.sleep(4)
        await page.goto("https://www.kartexpol.pl/pl/basket/step2", wait_until="networkidle")
        await asyncio.sleep(5)
        inputs = await page.evaluate("Array.from(document.querySelectorAll('input:not([type=hidden])')).map(e=>({n:e.name,p:e.placeholder,t:e.type})).filter(e=>e.n||e.p)")
        print(f"INPUTS:{json.dumps(inputs)}", flush=True)
        print(f"CAPTURED:{len(captured)}", flush=True)
        for c in captured:
            print(f"  {c['m']} {c['url']} {c['body'][:300]}", flush=True)
        await browser.close()
asyncio.run(t())
