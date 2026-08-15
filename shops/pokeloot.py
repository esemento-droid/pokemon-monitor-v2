import asyncio
import json
import subprocess

SHOP = "pokeloot"
API_URL = "https://www.pokeloot.pl/collections/wszystkie-produkty/products.json?limit=250"

EXCLUDE = [
    "sleeves", "album", "pro-binder", "portfolio", "toploader", "ultra pro", "deck box", "koszulk",
    "koreański", "korean", "s-chin", "chiński", "chinese", "figur", "japoński", "japońsk",
    "japanese", "battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "wcs ", "battle academy", "(jp)", "(chi)", "ultra-pro",
    "playmat", "segregator", "alcove", "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto",
    "star wars", "magic the gathering", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound", "zeszyt", "puzzle"
]

async def get_products():
    products = []
    try:
        result = subprocess.run(
            ["curl", "-sL", "--proxy", "http://127.0.0.1:8888", "--max-time", "30", "-H",
             "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
             API_URL],
            capture_output=True, text=True, timeout=35
        )
        if not result.stdout:
            return []
        data = json.loads(result.stdout)
    except Exception:
        return []

    for p in data.get("products", []):
        title = p.get("title", "")
        if any(ex in title.lower() for ex in EXCLUDE):
            continue

        variants = p.get("variants", [])
        if not variants:
            continue
        price_raw = variants[0].get("price", "0")
        try:
            price = f"{float(price_raw):.2f} PLN"
        except (ValueError, TypeError):
            price = "brak"

        available = any(v.get("available", False) for v in variants)
        pid = str(p.get("id", ""))
        images = p.get("images", [])
        image = images[0].get("src", "") if images else ""
        handle = p.get("handle", "")
        url = f"https://www.pokeloot.pl/products/{handle}" if handle else ""

        products.append({
            "id": f"pokeloot_{pid}",
            "name": title,
            "price": price,
            "shop": SHOP,
            "url": url,
            "image": image,
            "stock": 1 if available else 0,
            "available": available,
        })

    print(f"[POKELOOT] {len(products)} produktow")
    return products
