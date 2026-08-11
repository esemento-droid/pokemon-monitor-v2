#!/usr/bin/env python3
import asyncio, sys, os
sys.path.insert(0, "/opt/pokemon-monitor-v2")
os.chdir("/opt/pokemon-monitor-v2")
os.environ.setdefault("DISPLAY", ":99")

from shops.battlestash import get_products

async def test():
    print("Testing battlestash scraper...")
    prods = await get_products()
    print(f"RESULT: {len(prods)} products")
    for p in prods[:10]:
        print(f"  {p['name'][:60]} | {p['price']} | avail={p['available']}")
    # Check debug HTML
    debug = "/opt/pokemon-monitor-v2/data/battlestash_debug.html"
    if os.path.exists(debug):
        size = os.path.getsize(debug)
        with open(debug) as f:
            content = f.read(300)
        print(f"\nDEBUG HTML: {size} bytes")
        print(f"First 300 chars: {content}")
    else:
        print("\nNo debug HTML saved")

asyncio.run(test())
