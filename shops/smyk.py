import aiohttp
from bs4 import BeautifulSoup

SHOP = "smyk.com"
URLS = [
    "https://www.smyk.com/pl/pl/search?q=Pokemon%20tcg",
    "https://www.smyk.com/pl/pl/search?q=Pokemon",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept-Language": "pl-PL,pl;q=0.9",
}

TCG_KEYWORDS = ["pokemon tcg", "booster", "elite trainer box", "etb", "premium collection",
                "collection", "checklane", "blister", "tin", "promo card",
                "karta uzupelniajaca", "ultra-pro", "album na karty", "portfolio", "first partner", "illustration", "display"]

async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for url in URLS:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()
            except Exception:
                continue

            soup = BeautifulSoup(html, "lxml")
            items = soup.select(".complex-product")

            for item in items:
                text = item.get_text(" ", strip=True)
                low = text.lower()
                if "pokemon" not in low and "pokémon" not in low:
                    continue

                href = ""
                for a in item.select("a[href]"):
                    h = a.get("href", "")
                    if "/p/" in h:
                        href = h
                        break
                if not href:
                    continue
                if href.startswith("/"):
                    href = "https://www.smyk.com" + href

                pid = href.split("-i")[-1]
                if pid in seen:
                    continue
                seen.add(pid)

                name_tag = item.select_one(".complex-product__name")
                name = name_tag.get_text(" ", strip=True) if name_tag else ""

                name_low = name.lower()
                if not any(k in name_low for k in TCG_KEYWORDS):
                    continue

                price_tag = item.select_one(".complex-product__price")
                price = price_tag.get_text(" ", strip=True) if price_tag else ""

                img = item.find("img")
                image = ""
                if img:
                    # Try multiple attributes for full image URL
                    for attr in ("data-srcset", "data-src", "srcset", "src"):
                        val = img.get(attr, "")
                        if val and (".jpg" in val or ".png" in val or ".webp" in val):
                            # srcset may have multiple URLs, take first
                            image = val.split(",")[0].split(" ")[0].strip()
                            break
                    if not image:
                        image = img.get("data-src") or img.get("src", "")
                    if image and image.startswith("/"):
                        image = "https://www.smyk.com" + image

                available = "dodaj do koszyka" in low

                products.append({
                    "id": str(pid),
                    "shop": SHOP,
                    "name": name,
                    "price": price,
                    "url": href,
                    "image": image,
                    "stock": "Dostepny" if available else "Niedostepny",
                    "available": available,
                })

    print(f"[SMYK] razem: {len(products)}")
    return products
