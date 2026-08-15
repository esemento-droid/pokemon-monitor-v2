"""
Scraper: bookland.com.pl
Platform: Magento 2 (GraphQL API)
Method: aiohttp + proxy
Products: pokemon search (monitoring for TCG drops)
"""
import aiohttp
import json

SHOP = "bookland"
PROXY = "http://127.0.0.1:8888"
GRAPHQL_URL = "https://bookland.com.pl/graphql"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
}

EXCLUDE = [
    "piórnik", "piornik", "worek", "plecak", "zeszyt", "teczka", "crochet", "timelines",
    "podręcznik", "podrecznik", "saszetka", "kolorowe przygody", "battle deck",
    "league battle", "rival battle", "v battle", "world championship", "wcs deck", "wcs ",
    "battle academy", "japoński", "japońsk", "japanese", "(jp)", "koreański", "koreańsk",
    "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese", "ultra pro", "ultra-pro",
    "playmat", "portfolio", "pro-binder", "sleeves", "toploader", "album", "koszulk", "segregator",
    "deck box", "alcove", "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound", "puzzle", "figurk", "figure set"
]

QUERY = """{
  products(search: "pokemon", pageSize: 50) {
    total_count
    items {
      id
      name
      sku
      url_key
      stock_status
      price_range {
        minimum_price {
          final_price {
            value
            currency
          }
        }
      }
      small_image {
        url
      }
    }
  }
}"""


async def get_products():
    products = []
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            payload = json.dumps({"query": QUERY})
            async with session.post(
                GRAPHQL_URL,
                data=payload,
                proxy=PROXY,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
    except Exception:
        return []

    items = data.get("data", {}).get("products", {}).get("items", [])

    for item in items:
        name = item.get("name", "")
        if any(ex in name.lower() for ex in EXCLUDE):
            continue
        pid = str(item.get("id", ""))
        sku = item.get("sku", "")
        url_key = item.get("url_key", "")
        stock_status = item.get("stock_status", "")
        available = stock_status == "IN_STOCK"

        price_data = item.get("price_range", {}).get("minimum_price", {}).get("final_price", {})
        price_val = price_data.get("value")
        currency = price_data.get("currency", "PLN")
        price = f"{price_val:.2f} {currency}" if price_val else "brak"

        image = item.get("small_image", {}).get("url", "")
        url = f"https://bookland.com.pl/{url_key}" if url_key else ""

        products.append({
            "id": f"bookland_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": url,
            "image": image.replace(" ", "%20") if image else "",
            "stock": 1 if available else 0,
            "available": available,
        })

    print(f"[BOOKLAND] {len(products)} produktow")
    return products
