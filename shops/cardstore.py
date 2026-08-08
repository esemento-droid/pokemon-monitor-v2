"""
Scraper: cardstore.pl (PrestaShop 1.6)
Category: /658-pokemon-tcg
Method: aiohttp HTML
"""
import aiohttp
import re
from bs4 import BeautifulSoup

SHOP = "cardstore"
URL = "https://cardstore.pl/658-pokemon-tcg"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}

EXCLUDE = re.compile(
    r"koszulk|sleeve|album|toploader|binder|portfolio|playmat|mata do gry|deck.?box|ultra.?pro|dragon.?shield|gamegenic",
    re.IGNORECASE,
)

async def get_products():
    products = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(URL, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return products
            html = await resp.text()

    soup = BeautifulSoup(html, "html.parser")
    items = soup.select("li.ajax_block_product")

    for item in items:
        link_tag = item.select_one("a.product_img_link")
        if not link_tag:
            continue
        name = (link_tag.get("title") or "").strip()
        url = (link_tag.get("href") or "").strip()
        if not name or not url:
            continue

        if EXCLUDE.search(name):
            continue

        id_match = re.search(r"/(\d+)-", url)
        product_id = f"{SHOP}_{id_match.group(1)}" if id_match else f"{SHOP}_{name[:30]}"

        img_tag = item.select_one("img[itemprop='image']")
        image = (img_tag.get("src") or "") if img_tag else ""
        image = image.replace(" ", "%20")

        right_block = item.select_one(".right-block")
        price_tag = right_block.select_one("span[itemprop='price']") if right_block else None
        if not price_tag:
            price_tag = item.select_one("span[itemprop='price']")
        price_text = price_tag.get_text(strip=True) if price_tag else "brak"
        price_match = re.search(r"([\d\s]+[,.]?\d*)", price_text)
        if price_match:
            price_val = price_match.group(1).replace(" ", "").replace(",", ".")
            price = f"{price_val} zl"
        else:
            price = "brak"

        qty_tag = item.select_one("span.quantity")
        stock = None
        if qty_tag:
            qty_match = re.search(r"(-?\d+)", qty_tag.get_text())
            if qty_match:
                stock = int(qty_match.group(1))

        available = False
        add_btn = item.select_one("a.ajax_add_to_cart_button")
        if add_btn:
            available = True
        if stock is not None and stock <= 0:
            if not add_btn:
                available = False

        products.append({
            "id": product_id,
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": url,
            "image": image,
            "stock": stock if stock and stock > 0 else None,
            "available": available,
        })

    return products
