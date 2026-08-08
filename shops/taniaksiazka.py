import aiohttp
import re
import json

SHOP = "taniaksiazka"
URLS = [
    "https://www.taniaksiazka.pl/lego-pokemon-c-14623_14624_17518.html",
    "https://www.taniaksiazka.pl/szukaj?q=pokemon+tcg",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

async def get_products():
    products = []
    seen = set()
    jar = aiohttp.CookieJar()
    async with aiohttp.ClientSession(headers=HEADERS, cookie_jar=jar) as session:
        pokemon_ids = set()
        for url in URLS:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20), allow_redirects=True) as resp:
                    if resp.status != 200:
                        continue
                    raw = await resp.read()
                    html = raw.decode("utf-8", errors="ignore")
            except Exception:
                continue

            if "Brak produkt" in html:
                continue

            # Extract JSON product data embedded in page
            matches = re.findall(
                r'\{"id":"(\d+)","name":"([^"]+)"[^}]*?"unit_sale_price":([\d.]+),"url":"([^"]+)"[^}]*?"product_image_url":"([^"]*)"[^}]*?"availability":"([^"]+)"',
                html
            )
            is_category = "pokemon-c-" in url
            for pid, name, price, prod_url, image, avail in matches:
                if pid in seen:
                    continue
                if is_category:
                    pokemon_ids.add(pid)
                seen.add(pid)
                name = name.encode().decode("unicode_escape", errors="ignore")
                low = name.lower()
                if any(x in low for x in ["lorcana", "ninjago", "star wars", "harry potter", "magic the"]):
                    continue
                if "pokemon" not in low and "pokémon" not in low and pid not in pokemon_ids:
                    continue
                prod_url = prod_url.replace("\\/", "/")
                image = image.replace("\\/", "/")
                available = avail.lower() == "in stock"
                products.append({
                    "id": f"taniaksiazka_{pid}",
                    "name": name,
                    "price": f"{price} zl",
                    "shop": SHOP,
                    "url": prod_url,
                    "image": image,
                    "stock": 1 if available else 0,
                    "available": available,
                })
    print(f"[TANIAKSIAZKA] {len(products)} produktow")
    return products
