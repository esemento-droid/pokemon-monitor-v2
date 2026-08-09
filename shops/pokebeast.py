"""
Pokebeast.pl - scraper Pokemon ENG
Sklep na platformie Shoper - używa <product-tile> web components.
Obsługuje paginację po linkach rel='next'.
Gdy strona jest w przebudowie (503) zwraca [] bez crasha.
"""
import aiohttp
from bs4 import BeautifulSoup
import logging

log = logging.getLogger("monitor")

BASE = "https://pokebeast.pl"
CATEGORIES = [
    "/pl/c/Pokemon-ENG/48",
    "/pl/c/Pokemon-JPN/49",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}


async def get_products():
    products = []
    seen_ids = set()
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            for cat_path in CATEGORIES:
                for page in range(1, 15):
                    url = f"{BASE}{cat_path}" if page == 1 else f"{BASE}{cat_path}/{page}"
                    try:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30), ssl=False) as resp:
                            if resp.status == 503:
                                log.info("[pokebeast] Strona w przebudowie (503)")
                                return []
                            if resp.status != 200:
                                break
                            html = await resp.text()
                    except Exception as e:
                        log.warning(f"[pokebeast] Fetch error: {e}")
                        break

                    # Check for maintenance message
                    if "przebudow" in html.lower() or "za kilka dni" in html.lower():
                        log.info("[pokebeast] Strona w przebudowie")
                        return []

                    soup = BeautifulSoup(html, "lxml")
                    tiles = soup.select("product-tile")
                    if not tiles:
                        break
                    for tile in tiles:
                        pid = tile.get("product-id")
                        if not pid or pid in seen_ids:
                            continue
                        seen_ids.add(pid)
                        name = tile.get("name", "")
                        if not name or len(name) < 5:
                            continue
                        price_val = tile.get("price", "0")
                        try:
                            price = f"{float(price_val):.2f} zl" if price_val else "brak"
                        except (ValueError, TypeError):
                            price = "brak"
                        href_el = tile.select_one("a[href]")
                        href = href_el.get("href", "") if href_el else ""
                        product_url = f"{BASE}{href}" if href.startswith("/") else href
                        img_el = tile.select_one("img")
                        image = ""
                        if img_el:
                            image = img_el.get("data-src") or img_el.get("src", "")
                            if image and image.startswith("//"):
                                image = "https:" + image
                            elif image and image.startswith("/"):
                                image = BASE + image
                        txt = tile.get_text(" ", strip=True).lower()
                        available = "koszyk" in txt or "dodaj" in txt
                        products.append({
                            "id": f"pokebeast_{pid}",
                            "name": name,
                            "price": price,
                            "shop": "pokebeast",
                            "url": product_url,
                            "image": image,
                            "stock": 1 if available else 0,
                            "available": available,
                        })
                    # Check next page
                    if not soup.select_one("a.pagination_next, link[rel='next']"):
                        break
    except Exception as e:
        log.error(f"[pokebeast] Error: {e}")
    print(f"[pokebeast] {len(products)} produktow")
    return products
