#!/usr/bin/env python3
"""Diagnostyka smyk — co scraper widzi (produkty, obrazki, dostępność)"""
import asyncio
import sys
sys.path.insert(0, "/opt/pokemon-monitor-v2")
from shops.smyk import get_products

async def main():
    products = await get_products()
    print(f"\n=== SMYK: {len(products)} produktow ===\n")
    for p in products:
        avail = "✅" if p["available"] else "❌"
        img_ok = "IMG_OK" if p.get("image") and p["image"].startswith("http") else "NO_IMG"
        print(f"  {avail} {img_ok} | {p['name'][:60]}")
        print(f"       Price: {p['price']} | URL: {p['url'][:70]}")
        print(f"       Image: {p.get('image', '')[:80]}")
        print()

asyncio.run(main())
