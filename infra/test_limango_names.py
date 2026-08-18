#!/usr/bin/env python3
"""Show limango product names and check if they match promoklocki set numbers."""
import asyncio
import sys
import os
import re
import json
import ssl
import aiohttp

sys.path.insert(0, "/opt/pokemon-monitor-v2")

BASE = "https://www.limango.pl"
BROWSE_URL = f"{BASE}/shop/lego"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}
NEXT_DATA_RE = re.compile(r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

LEGO_SET_CATEGORIES = ["zestawy i zabawki konstrukcyjne", "klocki", "zabawki konstrukcyjne"]
TOY_PATH_KEYWORDS = ["zabawk", "klocki", "konstruk", "toys", "spielzeug"]

def is_lego_set(product):
    cat = (product.get("subCategoryName") or "").lower().strip()
    if cat and any(lc in cat for lc in LEGO_SET_CATEGORIES):
        return True
    if product.get("isOneSizeProduct"):
        for path in product.get("treePaths", []):
            if any(kw in path.lower() for kw in TOY_PATH_KEYWORDS):
                return True
    name = product.get("name", "")
    if re.search(r'\b\d{5}\b', name):
        for path in product.get("treePaths", []):
            if any(kw in path.lower() for kw in TOY_PATH_KEYWORDS):
                return True
    clothing = ["bokser", "kurtk", "spodni", "bluza", "piżam", "skarpet", "czapk", "szalik", "t-shirt", "koszulk", "dress"]
    if any(kw in name.lower() for kw in clothing):
        return False
    return False

async def main():
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    products = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for page in range(1, 7):
            url = f"{BROWSE_URL}?page={page}" if page > 1 else BROWSE_URL
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30), ssl=ssl_ctx) as resp:
                if resp.status != 200:
                    break
                html = await resp.text()
            match = NEXT_DATA_RE.search(html)
            if not match:
                break
            data = json.loads(match.group(1))
            listing = data["props"]["pageProps"]["preloadedState"]["listing"]
            page_products = listing["products"]["data"]
            if not page_products:
                break
            for item in page_products:
                if is_lego_set(item):
                    name = item.get("name", "")
                    variant = item.get("cheapestVariantWithStock") or {}
                    price = variant.get("salesPrice", {}).get("amount", 0)
                    set_match = re.search(r'\b(\d{5})\b', name)
                    set_num = set_match.group(1) if set_match else None
                    products.append({
                        "name": name,
                        "price": price,
                        "set_number": set_num,
                    })
            if len(page_products) < 50:
                break

    # Show ALL products with and without set numbers
    with_num = [p for p in products if p["set_number"]]
    without_num = [p for p in products if not p["set_number"]]

    print(f"=== LIMANGO LEGO PRODUCTS: {len(products)} total ===")
    print(f"  WITH set number: {len(with_num)}")
    print(f"  WITHOUT set number: {len(without_num)}")
    print()

    print("--- WITH SET NUMBER (promoklocki.pl/{number}) ---")
    for p in with_num:
        print(f"  #{p['set_number']} | {p['price']:.2f} zl | {p['name']}")
    print()

    print("--- WITHOUT SET NUMBER (cannot match to promoklocki) ---")
    for p in without_num[:30]:
        print(f"  ???? | {p['price']:.2f} zl | {p['name']}")
    if len(without_num) > 30:
        print(f"  ... +{len(without_num)-30} more")

asyncio.run(main())
