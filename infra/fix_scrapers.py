#!/usr/bin/env python3
"""Test broken scrapers one by one — diagnose why they fail on VPS."""
import asyncio
import sys
import os
import traceback
import time

sys.path.insert(0, "/opt/pokemon-monitor-v2")
os.environ.setdefault("DISPLAY", ":99")

BROKEN = ["rgfk", "eduksiazka", "xjoy", "gralnia", "dystryktzero", "mepel", "am76", "mediaexpert"]

async def test_shop(name):
    print(f"\n{'='*60}")
    print(f"  TESTING: {name}")
    print(f"{'='*60}")
    start = time.time()
    try:
        import importlib
        module = importlib.import_module(f"shops.{name}")
        get_fn = module.get_products
        if asyncio.iscoroutinefunction(get_fn):
            products = await asyncio.wait_for(get_fn(), timeout=60)
        else:
            products = get_fn()
        elapsed = time.time() - start
        if products:
            print(f"  ✅ OK: {len(products)} products in {elapsed:.1f}s")
            for p in products[:3]:
                print(f"     {p.get('name','?')[:50]} | {p.get('price','?')} | avail={p.get('available')}")
        else:
            print(f"  ⚠️ EMPTY: 0 products in {elapsed:.1f}s")
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        print(f"  ❌ TIMEOUT after {elapsed:.1f}s")
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ❌ ERROR ({elapsed:.1f}s): {type(e).__name__}: {e}")
        traceback.print_exc(limit=3)

async def main():
    # Test specific shop or all broken
    targets = sys.argv[1:] if len(sys.argv) > 1 else BROKEN
    print(f"Testing {len(targets)} shops: {', '.join(targets)}")
    for name in targets:
        await test_shop(name)
    print(f"\n{'='*60}")
    print("  ALL TESTS DONE")
    print(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(main())
