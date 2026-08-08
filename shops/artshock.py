import aiohttp
from bs4 import BeautifulSoup

CATEGORY_URL = "https://artshock.pl/karciane,c671,96,1,pl.html"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

EXCLUDE = ["ultra pro", "album", "sleeves", "deck protector", "one-touch", "portfolio",
           "wykrywacz", "interaktywna", "panini", "fifa", "minecraft", "poker", "kick-off"]

async def get_products():
    products = []
    async with aiohttp.ClientSession() as session:
        async with session.get(CATEGORY_URL, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            html = await resp.text()

    soup = BeautifulSoup(html, "lxml")

    for tile in soup.select("div.abs-layout-product-gallery"):
        try:
            pid = tile.get("data-offer-position-id", "")
            if not pid:
                continue

            name_tag = tile.select_one("h3.abs-product-name a")
            if not name_tag:
                continue
            name = name_tag.get_text(" ", strip=True)

            additional = tile.select_one("p.abs-additional-name")
            if additional:
                add_text = additional.get_text(" ", strip=True)
                if add_text:
                    name = f"{name} {add_text}"

            name_lower = name.lower()

            # Must contain pokemon
            if "pokemon" not in name_lower and "pokémon" not in name_lower:
                continue

            # Exclude accessories/non-TCG
            if any(ex in name_lower for ex in EXCLUDE):
                continue

            # Price
            price_tag = tile.select_one(".abs-item-price-amount")
            price = "brak"
            if price_tag:
                price_text = price_tag.get_text(" ", strip=True)
                # Extract just "229,00 zł"
                parts = price_text.split()
                if len(parts) >= 2:
                    price = f"{parts[0]} {parts[1]}"

            # Availability
            stock_tag = tile.select_one(".stock-name")
            stock_text = stock_tag.get_text(strip=True) if stock_tag else ""
            available = "dostępne" in stock_text.lower()

            # URL
            url = name_tag.get("href", "")
            if url and not url.startswith("http"):
                url = f"https://artshock.pl{url}"

            # Image
            img_tag = tile.select_one("img[ci-src]")
            image = ""
            if img_tag:
                img_src = img_tag.get("ci-src", "")
                if img_src:
                    image = f"https:{img_src}" if img_src.startswith("//") else img_src

            products.append({
                "id": f"artshock_{pid}",
                "name": name,
                "price": price,
                "shop": "artshock",
                "url": url,
                "image": image,
                "stock": stock_text if stock_text else "Brak",
                "available": available,
            })
        except Exception:
            continue

    print(f"[ARTSHOCK] Znaleziono produktów: {len(products)}")
    return products
