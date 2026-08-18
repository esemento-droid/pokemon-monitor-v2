#!/usr/bin/env python3
"""Test limango live — run scraper, show what it finds, check price compare."""
import asyncio
import sys
import os
sys.path.insert(0, "/opt/pokemon-monitor-v2")
os.chdir("/opt/pokemon-monitor-v2")

async def main():
    from shops.limango import get_products
    print("Running limango scraper...")
    products = await get_products()
    
    avail = [p for p in products if p.get("available")]
    matched = [p for p in products if p.get("price_compare")]
    
    print(f"\nTotal: {len(products)}")
    print(f"Available: {len(avail)}")
    print(f"Price matched (promoklocki): {len(matched)}")
    print()
    
    if matched:
        print("--- WITH PRICE COMPARE ---")
        for p in matched[:10]:
            print(f"  {p['name'][:55]}")
            print(f"    Limango: {p['price']} | Set #{p.get('set_number')}")
            print(f"    Promoklocki: {p['price_compare']}")
            print(f"    Link: {p['url'][:60]}")
            print()
    else:
        print("--- NO PRICE MATCHES (cache empty or sitemap issue) ---")
    
    print("--- FIRST 10 AVAILABLE (all) ---")
    for p in avail[:10]:
        pc = p.get('price_compare', 'NO MATCH')
        print(f"  {p['name'][:55]} | {p['price']} | set={p.get('set_number','?')} | {pc[:40]}")
    
    # Check what's in DB for limango
    print("\n--- DB STATE ---")
    try:
        from database import init_db, get_shop_products
        await init_db()
        old = await get_shop_products("limango")
        print(f"  Products in DB: {len(old)}")
        if old:
            print(f"  (already has snapshot — changes will trigger events)")
        else:
            print(f"  (EMPTY — first scan = SNAPSHOT, no Discord events!)")
            print(f"  → Need second scan to detect changes")
    except Exception as e:
        print(f"  DB error: {e}")

asyncio.run(main())
