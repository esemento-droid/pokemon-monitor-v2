#!/usr/bin/env python3
"""Debug tcgumisia: fetch page, show availability parsing for 30th ETB."""
import asyncio
import sys
sys.path.insert(0, "/opt/pokemon-monitor-v2")
from shops.tcgumisia import get_products

async def main():
    products = await get_products()
    print(f"\nTotal products: {len(products)}")
    print(f"Available: {sum(1 for p in products if p['available'])}")
    print(f"Unavailable: {sum(1 for p in products if not p['available'])}")
    print("\n--- 30th products ---")
    for p in products:
        if "30th" in p["name"].lower() or "30 " in p["name"].lower() or "celebration" in p["name"].lower():
            status = "✅ AVAIL" if p["available"] else "❌ OOS"
            print(f"  {status} | {p['name']} | {p['price']} | {p['url']}")
    print("\n--- ALL available ---")
    for p in products:
        if p["available"]:
            print(f"  ✅ {p['name']} | {p['price']}")

asyncio.run(main())
