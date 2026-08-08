"""
Scraper: planetaprezent.pl
Silnik: Shopify JSON API
Metoda: subprocess curl (aiohttp blokowany przez Shopify)
Cooldown: 5 min
"""
import asyncio
import logging
import time
import json
import subprocess

logger = logging.getLogger(__name__)
SHOP = "planetaprezent.pl"
API_URL = "https://planetaprezent.pl/collections/pokemon-tcg/products.json?limit=250"
EXCLUDE_KEYWORDS = [
    "album", "deck box", "pudelko", "pudełko", "sleeve", "protector",
    "koszulk", "toploader", "segregator", "binder", "folder",
    "jap)", "(jap", "mini portfolio", "portfolio + booster",
    "zestaw koszulek", "accessory bundle",
]
COOLDOWN = 300
_last_fetch = 0
_last_result = []


async def get_products():
    global _last_fetch, _last_result
    if time.time() - _last_fetch < COOLDOWN and _last_result:
        return _last_result
    products = []
    try:
        result = subprocess.run(
            ["curl", "-s", "-H", "User-Agent: Mozilla/5.0", API_URL],
            capture_output=True, text=True, timeout=30
        )
        if not result.stdout:
            logger.error("[planetaprezent] Pusta odpowiedz")
            return _last_result if _last_result else products
        data = json.loads(result.stdout)
        for p in data.get("products", []):
            title = p.get("title", "")
            if any(kw in title.lower() for kw in EXCLUDE_KEYWORDS):
                continue
            variants = p.get("variants", [{}])
            variant = variants[0] if variants else {}
            price_raw = variant.get("price", "0")
            try:
                price = f"{float(price_raw):.2f} PLN"
            except (ValueError, TypeError):
                price = "brak"
            available = variant.get("available", False)
            pid = str(p.get("id", ""))
            images = p.get("images", [])
            image = images[0].get("src", "") if images else ""
            handle = p.get("handle", "")
            url = f"https://planetaprezent.pl/products/{handle}" if handle else ""
            products.append({
                "id": f"planetaprezent_{pid}",
                "name": title,
                "price": price,
                "shop": SHOP,
                "url": url,
                "image": image,
                "stock": 1 if available else 0,
                "available": available,
            })
    except Exception as e:
        logger.error(f"[planetaprezent] Error: {e}")
    if products:
        _last_fetch = time.time()
        _last_result = products
    logger.info(f"[planetaprezent] {len(products)} produktow ({sum(1 for p in products if p['available'])} avail)")
    return products
