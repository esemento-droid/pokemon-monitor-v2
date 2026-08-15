import aiohttp
import asyncio
import re
import json
import html

SHOP = "japancollectibles"
BASE = "https://japancollectibles.shop"
CAT_URL = f"{BASE}/Angielskie-Karty-Pokemon"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
EXCLUDE = [
    "sleeves", "koszulk", "toploader", "playmat", "album", "portfolio", "pro-binder", "one piece",
    "dragon ball", "naruto", "lorcana", "energii", "mystery pack", "deck box", "ultra pro",
    "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "battle academy", "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "ultra-pro", "segregator", "alcove", "yu-gi-oh", "digimon", "star wars",
    "magic the gathering", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound", "zeszyt", "puzzle", "figurk", "figure set"
]


def parse_gtag(page_html):
    """Parse gtag view_item_list - handles &amp; in product names."""
    items = []
    # Match the full gtag call including the JSON object (may contain ; in &amp;)
    m = re.search(r"gtag\('event',\s*'view_item_list',\s*(\{.*?\})\);", page_html)
    if m:
        raw_json = m.group(1)
        # Unescape HTML entities (&amp; -> &, etc)
        raw_json = html.unescape(raw_json)
        try:
            data = json.loads(raw_json)
            items = data.get("items", [])
        except (json.JSONDecodeError, KeyError):
            pass
    return items


async def get_products():
    products = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # First page + detect max page
        async with session.get(CAT_URL, timeout=aiohttp.ClientTimeout(total=30)) as r:
            first_html = await r.text()

        max_page = 1
        for m in re.findall(r'/Angielskie-Karty-Pokemon/pa/(\d+)', first_html):
            p = int(m)
            if p > max_page:
                max_page = p

        pages_html = [first_html]
        if max_page > 1:
            async def fetch_page(pg):
                try:
                    async with session.get(f"{CAT_URL}/pa/{pg}", timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        return await resp.text()
                except Exception:
                    return ""
            tasks = [fetch_page(pg) for pg in range(2, max_page + 1)]
            pages_html += await asyncio.gather(*tasks)

        seen_ids = set()
        for page_html in pages_html:
            if not page_html:
                continue
            items = parse_gtag(page_html)

            # Get product URLs from HTML
            url_map = {}
            for link_m in re.finditer(r'href="((?:https://japancollectibles\.shop)?/[^"]*-p(\d+))"', page_html):
                url_map[link_m.group(2)] = link_m.group(1)

            # Get images - data-src with product link context
            img_map = {}
            for img_m in re.finditer(r'<a[^>]*href="[^"]*-p(\d+)"[^>]*>.*?<img[^>]*(?:data-src|src)="([^"]*upload/[^"]*)"', page_html, re.DOTALL):
                img_map[img_m.group(1)] = img_m.group(2)

            for item in items:
                pid = str(item.get("item_id", ""))
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)

                name = item.get("item_name", "")
                if not name:
                    continue
                name_low = name.lower()
                if any(ex in name_low for ex in EXCLUDE):
                    continue

                price_val = item.get("price", 0)
                price = f"{price_val:.2f} zl" if price_val else "brak"
                quantity = item.get("quantity", 0)
                available = quantity > 0

                url = url_map.get(pid, "")
                if url and not url.startswith("http"):
                    url = BASE + url

                image = img_map.get(pid, "")
                if image and not image.startswith("http"):
                    image = BASE + image

                products.append({
                    "id": f"{SHOP}_{pid}",
                    "name": name,
                    "price": price,
                    "shop": SHOP,
                    "url": url,
                    "image": image,
                    "stock": quantity if quantity > 0 else None,
                    "available": available,
                })
    return products


if __name__ == "__main__":
    async def test():
        prods = await get_products()
        avail = [p for p in prods if p["available"]]
        print(f"Total: {len(prods)}, available: {len(avail)}")
        for p in prods[:15]:
            print(f"  {p['id']} | {p['name'][:50]} | {p['price']} | avail={p['available']} | stock={p['stock']}")
        print("...")
        # Show 30th products
        print("\n=== 30th / celebration / first partner ===")
        for p in prods:
            nl = p['name'].lower()
            if any(kw in nl for kw in ['30', 'celebr', 'first partner', 'anniversary']):
                print(f"  {p['id']} | {p['name'][:60]} | {p['price']} | avail={p['available']}")
    asyncio.run(test())
