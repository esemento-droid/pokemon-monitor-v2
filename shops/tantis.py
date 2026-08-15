import asyncio
import json
import re
from patchright.async_api import async_playwright

SHOP = "tantis"
BASE_URL = "https://tantis.pl"
EXCLUDE = [
    "ultra-pro", "ultra pro", "playmat", "portfolio", "binder", "deck box", "sleeves",
    "toploader", "album", "lalie", "nihil", "historia pokemon", "niezbędnik", "puzzle",
    "pokemon go", "karty do kolekc", "alcove", "symphonia", "synmphonia", "battle deck",
    "league battle", "rival battle", "v battle", "world championship", "wcs deck", "wcs ",
    "battle academy", "japoński", "japońsk", "japanese", "(jp)", "koreański", "koreańsk",
    "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese", "koszulk", "segregator",
    "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound", "zeszyt", "figurk", "figure set"
]

JS_FETCH_JSON = """
async (path) => {
    const r = await fetch(path, {
        headers: {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        credentials: 'same-origin'
    });
    if (!r.ok) return '[]';
    return await r.text();
}
"""

MAX_RETRIES = 2

async def get_products():
    for attempt in range(MAX_RETRIES + 1):
        try:
            return await _scrape()
        except Exception as e:
            err = str(e)
            if ("closed" in err or "crashed" in err or "Target" in err) and attempt < MAX_RETRIES:
                print(f"[TANTIS] Attempt {attempt+1} failed ({err}), retrying...")
                await asyncio.sleep(3)
                continue
            print(f"[TANTIS] Error: {e}")
            return []
    return []


async def _scrape():
    products = []
    seen_ids = set()
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            proxy={"server": "http://127.0.0.1:8888"},
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage']
        )
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        try:
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)
            # Wait for CF challenge
            for _ in range(8):
                title = await page.title()
                if "moment" not in title.lower() and "checking" not in title.lower():
                    break
                await asyncio.sleep(2)
            await asyncio.sleep(1)

            # Source 1: Category API (gives ~10 products with full details)
            try:
                raw = await page.evaluate(JS_FETCH_JSON, "/front-api/v1/products?categoryId=7053&limit=100")
                items = json.loads(raw)
                if isinstance(items, list):
                    for item in items:
                        pid = item.get("productId")
                        if pid and pid not in seen_ids:
                            seen_ids.add(pid)
                            _add_product(products, item)
            except Exception as e1:
                print(f"[TANTIS] Category API error: {e1}")

            # Source 2: Search autocomplete (gives 10 more, some overlap)
            try:
                raw = await page.evaluate(JS_FETCH_JSON, "/front-api/v1/search/autocomplete?query=pokemon+tcg")
                data = json.loads(raw)
                for r in data.get("item", {}).get("results", []):
                    attrs = r.get("attributes", {})
                    pid_str = r.get("url", "")
                    pid_match = re.search(r"i(\d+)", pid_str)
                    if not pid_match:
                        continue
                    pid = int(pid_match.group(1))
                    if pid in seen_ids:
                        continue
                    seen_ids.add(pid)
                    name_list = attrs.get("name", [])
                    name = name_list[0] if isinstance(name_list, list) and name_list else str(name_list)
                    name_low = name.lower()
                    if any(ex in name_low for ex in EXCLUDE):
                        continue
                    if "pokemon" not in name_low and "pokémon" not in name_low:
                        continue
                    price_str = attrs.get("price", "brak")
                    price_amount = attrs.get("price_amount", 0)
                    price = f"{price_amount:.2f} PLN" if price_amount else str(price_str)
                    img_list = attrs.get("images_urls_json", [])
                    image = img_list[0] if img_list else ""
                    web_url = attrs.get("web_url", [""])[0] if isinstance(attrs.get("web_url"), list) else ""
                    url = f"{BASE_URL}{web_url}" if web_url else ""
                    products.append({
                        "id": f"tantis_{pid}",
                        "name": name,
                        "price": price,
                        "shop": SHOP,
                        "url": url,
                        "image": image,
                        "stock": None,
                        "available": True,
                    })
            except Exception as e2:
                print(f"[TANTIS] Search API error: {e2}")

        finally:
            await browser.close()
    return products


def _add_product(products, item):
    """Add a product from category API format."""
    name = item.get("name", "")
    name_low = name.lower()
    if any(ex in name_low for ex in EXCLUDE):
        return
    if "pokemon" not in name_low and "pokémon" not in name_low:
        return
    pid = item.get("productId")
    if not pid:
        return
    price_val = item.get("price", 0)
    price = f"{price_val:.2f} PLN" if price_val else "brak"
    available = item.get("available", False)
    url = item.get("url", "")
    if url and not url.startswith("http"):
        url = f"{BASE_URL}{url}"
    image = ""
    img_data = item.get("image")
    if isinstance(img_data, dict):
        image = img_data.get("url", "")
    elif isinstance(img_data, str):
        image = img_data
    buy_limit = item.get("buyLimit")
    stock = buy_limit if buy_limit else None
    products.append({
        "id": f"tantis_{pid}",
        "name": name,
        "price": price,
        "shop": SHOP,
        "url": url,
        "image": image,
        "stock": stock,
        "available": available,
    })
