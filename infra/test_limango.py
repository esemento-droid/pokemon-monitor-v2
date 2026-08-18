#!/usr/bin/env python3
"""Test limango scraper — show what data we get and what's missing."""
import asyncio
import sys
import os
import json
import re
import aiohttp
import ssl

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

async def main():
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Fetch page 1
        async with session.get(BROWSE_URL, timeout=aiohttp.ClientTimeout(total=30), ssl=ssl_ctx) as resp:
            if resp.status != 200:
                print(f"ERROR: HTTP {resp.status}")
                return
            html = await resp.text()

        match = NEXT_DATA_RE.search(html)
        if not match:
            print("ERROR: No __NEXT_DATA__ found")
            return

        data = json.loads(match.group(1))
        listing = data["props"]["pageProps"]["preloadedState"]["listing"]
        products = listing["products"]["data"]
        pagination = listing["products"].get("pagination", {})

        print(f"=== LIMANGO DATA ANALYSIS ===")
        print(f"Total products in category: {pagination.get('totalCount', '?')}")
        print(f"Products on page 1: {len(products)}")
        print()

        # Show first 5 products with ALL fields
        print("--- FIRST 5 PRODUCTS (full data) ---")
        for i, item in enumerate(products[:5]):
            print(f"\n  Product {i+1}:")
            print(f"    ID: {item.get('id')}")
            print(f"    subCategoryName: {item.get('subCategoryName')}")
            print(f"    brand: {item.get('brand')}")
            # Check ALL available fields
            for key in sorted(item.keys()):
                if key not in ('images', 'cheapestVariantWithStock'):
                    val = item[key]
                    if isinstance(val, str) and len(val) > 100:
                        val = val[:100] + "..."
                    print(f"    {key}: {val}")
            # Variant info
            variant = item.get("cheapestVariantWithStock", {})
            if variant:
                print(f"    variant.name: {variant.get('name')}")
                print(f"    variant.ean: {variant.get('ean')}")
                print(f"    variant.sku: {variant.get('sku')}")
                print(f"    variant.salesPrice: {variant.get('salesPrice')}")
                print(f"    variant.originalPrice: {variant.get('originalPrice')}")
                # Check ALL variant fields
                for key in sorted(variant.keys()):
                    if key not in ('salesPrice', 'originalPrice', 'name', 'ean', 'sku'):
                        print(f"    variant.{key}: {variant[key]}")
            # Image URL
            images = item.get("images", {})
            default = images.get("default", {})
            url_template = default.get("url", "")
            print(f"    image_url_template: {url_template[:100]}")
            print()

        # Show product detail page for first available product
        print("\n--- PRODUCT DETAIL PAGE TEST ---")
        first_available = None
        for item in products:
            variant = item.get("cheapestVariantWithStock", {})
            price = variant.get("salesPrice", {}).get("amount")
            if price and price > 0:
                first_available = item
                break

        if first_available:
            pid = first_available["id"]
            numeric_id = pid.split("_")[-1] if "_" in pid else pid
            detail_url = f"{BASE}/p/{numeric_id}"
            print(f"  Fetching: {detail_url}")
            try:
                async with session.get(detail_url, timeout=aiohttp.ClientTimeout(total=15), ssl=ssl_ctx) as resp:
                    if resp.status == 200:
                        detail_html = await resp.text()
                        # Look for set number patterns
                        set_numbers = re.findall(r'\b(\d{5})\b', detail_html[:5000])
                        title_match = re.search(r'<title[^>]*>(.*?)</title>', detail_html)
                        h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', detail_html, re.DOTALL)
                        # Look for product name in NEXT_DATA
                        detail_next = NEXT_DATA_RE.search(detail_html)
                        if detail_next:
                            detail_data = json.loads(detail_next.group(1))
                            pp = detail_data.get("props", {}).get("pageProps", {})
                            product_detail = pp.get("preloadedState", {}).get("product", {})
                            print(f"  title: {title_match.group(1)[:100] if title_match else 'N/A'}")
                            print(f"  h1: {h1_match.group(1).strip()[:100] if h1_match else 'N/A'}")
                            print(f"  5-digit numbers in page: {set_numbers[:10]}")
                            # Show product detail keys
                            if product_detail:
                                print(f"  Detail keys: {list(product_detail.keys())[:20]}")
                                name = product_detail.get("name") or product_detail.get("title", "")
                                print(f"  Detail name: {name}")
                                desc = product_detail.get("description", "")[:200]
                                print(f"  Detail desc: {desc}")
                        else:
                            print(f"  No NEXT_DATA on detail page")
                            print(f"  title: {title_match.group(1)[:100] if title_match else 'N/A'}")
                    else:
                        print(f"  HTTP {resp.status}")
            except Exception as e:
                print(f"  Error: {e}")

    print("\n=== DONE ===")

asyncio.run(main())
