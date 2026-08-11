#!/usr/bin/env python3
"""List available tcgumisia products from DB."""
import asyncio, sys, os
sys.path.insert(0, "/opt/pokemon-monitor-v2")
os.chdir("/opt/pokemon-monitor-v2")
from database import init_db, get_shop_products

async def main():
    await init_db()
    prods = await get_shop_products("tcgumisia.pl")
    avail = [p for p in prods.values() if p.get("available")]
    print(f"Total: {len(prods)}, Available: {len(avail)}")
    for p in sorted(avail, key=lambda x: x.get("name", ""))[:15]:
        print(f"  {p['name'][:55]:55s} | {p['price']:12s} | {p['url']}")

asyncio.run(main())
