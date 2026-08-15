import asyncio
import re
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

SHOP = "dragonus"
BASE = "https://dragonus.pl"
CAT_URL = f"{BASE}/pl/c/Pokemon/315"
EXCLUDE = [
    "sleeve", "koszulk", "toploader", "playmat", "ultra pro", "one piece", "naruto",
    "dragon ball", "magic:", "mtg:", "lorcana", "yu-gi-oh", "portfolio", "pro-binder",
    "binder", "album", "deck box", "energii", "ygo", "academy", "accessory", "flip out",
    "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "japoński", "japońsk", "japanese", "(jp)", "koreański", "koreańsk",
    "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese", "ultra-pro", "segregator",
    "alcove", "digimon", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"
]

async def get_products():
    for _att in range(2):
        try:
            return await _do_scrape()
        except Exception as e:
            print("[dragonus] Retry " + str(_att+1) + "/2: " + type(e).__name__)
            await asyncio.sleep(5)
    return []

async def _do_scrape():
    products = []
    pages_html = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        async def fetch_page(pg):
            ctx = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
            page = await ctx.new_page()
            url = f"{CAT_URL}/{pg}" if pg > 1 else CAT_URL
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(4)
                html = await page.content()
                return html
            finally:
                await page.close()
                await ctx.close()

        # First page to detect max
        html1 = await fetch_page(1)
        max_page = 1
        for m in re.findall(r'/pl/c/Pokemon/315/(\d+)', html1):
            pg = int(m)
            if pg > max_page:
                max_page = pg

        pages_html = [html1]
        # Parallel fetch remaining pages
        if max_page > 1:
            results = await asyncio.gather(*[fetch_page(pg) for pg in range(2, max_page + 1)])
            pages_html += results

        await browser.close()

    for page_html in pages_html:
        soup = BeautifulSoup(page_html, "lxml")
        for r in soup.select("td.even, td.odd"):
            name_el = r.select_one("span.productname")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            name_low = name.lower()
            if any(ex in name_low for ex in EXCLUDE):
                continue
            link = r.select_one('a[href*="/pl/p/"]')
            href = link["href"] if link and link.get("href") else ""
            pid_m = re.search(r'/(\d+)$', href)
            pid = pid_m.group(1) if pid_m else ""
            if not pid:
                continue
            url = BASE + href if href.startswith("/") else href
            img = r.select_one("img[data-src]") or r.select_one("img[src*=product]")
            image = ""
            if img:
                image = img.get("data-src") or img.get("src") or ""
                if image and not image.startswith("http"):
                    image = BASE + image
            price_el = r.select_one(".price em") or r.select_one("em")
            price = price_el.get_text(strip=True) if price_el else ""
            available = "basket/add" in str(r)
            products.append({
                "id": f"{SHOP}_{pid}",
                "name": name,
                "price": price,
                "shop": SHOP,
                "url": url,
                "image": image,
                "stock": None,
                "available": available,
            })
    return products

if __name__ == "__main__":
    async def test():
        prods = await get_products()
        avail = [p for p in prods if p["available"]]
        print(f"Total: {len(prods)}, available: {len(avail)}")
        for p in prods[:10]:
            print(f"  {p['id']} | {p['name'][:50]} | {p['price']} | avail={p['available']}")
    asyncio.run(test())
