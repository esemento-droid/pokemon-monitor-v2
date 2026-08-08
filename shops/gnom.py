import aiohttp
import json

URL = "https://gnom-sklep.pl/graphql/v1/"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json",
    "Accept": "application/json",
}
QUERY = '''{
  products(
    searchInput:{text:"Pokemon TCG"}
    settingsInput:{limit:100}
  ){
    products{
      id
      name
      link
      icon
      price{price{gross{value}}}
      sizes{amount availability{status}}
    }
  }
}'''
EXCLUDE = ["naruto", "ultra pro", "sleeve", "portfolio", "binder", "deck box", "toploader"]

async def get_products():
    products = []
    data = None
    async with aiohttp.ClientSession() as session:
        for attempt in range(3):
            try:
                async with session.post(URL, headers=HEADERS,
                                        json={"query": QUERY},
                                        timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        print(f"[GNOM] HTTP {resp.status}, attempt {attempt+1}")
                        continue
                    data = await resp.json()
                    if "errors" in data:
                        print(f"[GNOM] GraphQL error: {data['errors'][0].get('message','?')[:60]}")
                        continue
                    break
            except Exception as e:
                print(f"[GNOM] {type(e).__name__}: {str(e)[:60]}, attempt {attempt+1}")
                if attempt < 2:
                    import asyncio
                    await asyncio.sleep(2)
                continue
    if not data or "data" not in data:
        print("[GNOM] ERROR: no data after 3 attempts")
        return []
    items = data.get("data", {}).get("products", {}).get("products", [])
    for p in items:
        name = p.get("name", "")
        if any(ex in name.lower() for ex in EXCLUDE):
            continue
        sizes = p.get("sizes") or []
        stock = 0
        available = False
        if sizes:
            stock = sizes[0].get("amount", 0) or 0
            status = sizes[0].get("availability", {}).get("status", "")
            available = stock > 0 and status in ["enable", "preorder"]
        price = "brak"
        try:
            price = f"{p['price']['price']['gross']['value']} PLN"
        except (KeyError, TypeError):
            pass
        image = p.get("icon", "")
        if image and image.startswith("/"):
            image = "https://gnom-sklep.pl" + image
        products.append({
            "id": str(p["id"]),
            "name": name,
            "price": price,
            "shop": "gnom-sklep.pl",
            "url": p.get("link", ""),
            "image": image,
            "stock": stock,
            "available": available,
        })
    print(f"[GNOM] {len(products)} produktow")
    return products
