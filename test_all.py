#!/usr/bin/env python3
"""Test all scrapers - speed, products, errors."""
import asyncio
import sys
import time
import importlib
import os

sys.path.insert(0, "/opt/pokemon-monitor-v2")
os.chdir("/opt/pokemon-monitor-v2")


async def test_shop(name, module, sem):
    async with sem:
        start = time.time()
        try:
            fn = module.get_products
            if asyncio.iscoroutinefunction(fn):
                prods = await fn()
            else:
                loop = asyncio.get_event_loop()
                prods = await loop.run_in_executor(None, fn)
            elapsed = time.time() - start
            cnt = len(prods) if prods else 0
            avail = len([p for p in prods if p.get("available")]) if prods else 0
            return (name, cnt, avail, elapsed, None)
        except Exception as e:
            elapsed = time.time() - start
            return (name, 0, 0, elapsed, str(e)[:50])


async def main():
    shops = []
    for f in sorted(os.listdir("shops")):
        if not f.endswith(".py") or f.startswith("__"):
            continue
        if f in ("base.py", "template.py"):
            continue
        name = f[:-3]
        try:
            m = importlib.import_module(f"shops.{name}")
            if hasattr(m, "get_products"):
                shops.append((name, m))
        except Exception as e:
            print(f"LOAD ERROR: {name} - {e}")

    print(f"Testing {len(shops)} shops...\n")
    sem = asyncio.Semaphore(10)
    tasks = [test_shop(n, m, sem) for n, m in shops]
    results = await asyncio.gather(*tasks)
    results.sort(key=lambda x: -x[3])

    print(f"{'SHOP':<20} {'PROD':>5} {'AVAIL':>5} {'TIME':>7} ERROR")
    print("-" * 65)
    total_prod = 0
    total_avail = 0
    for name, cnt, avail, t, err in results:
        total_prod += cnt
        total_avail += avail
        flag = "!!!" if t > 30 else ("! " if t > 10 else "  ")
        e = err[:30] if err else ""
        print(f"{flag}{name:<18} {cnt:>5} {avail:>5} {t:>6.1f}s {e}")

    errs = [r for r in results if r[4]]
    zeros = [r for r in results if r[1] == 0 and not r[4]]
    slow = [r for r in results if r[3] > 30]
    print(f"\n{'='*65}")
    print(f"TOTAL: {len(results)} shops | {total_prod} products | {total_avail} available")
    print(f"ERRORS: {len(errs)} | ZERO: {len(zeros)} | SLOW(>30s): {len(slow)}")
    if errs:
        print(f"\nERRORS:")
        for name, _, _, t, err in errs:
            print(f"  {name}: {err}")
    if zeros:
        print(f"\nZERO PRODUCTS:")
        for name, _, _, t, _ in zeros:
            print(f"  {name} ({t:.1f}s)")


if __name__ == "__main__":
    asyncio.run(main())
