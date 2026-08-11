#!/usr/bin/env python3
"""
Pokemon Monitor v2 — 8-HOUR ENDURANCE TEST
===========================================
Tests ALL scrapers in a loop for 8 hours.
Each round: scrapes all shops, reports results.
Saves per-round stats and final summary.

Usage: python3 test_8h.py 2>&1 | tee /opt/pokemon-monitor-v2/data/test_8h.log
"""

import asyncio
import sys
import time
import importlib
import os
import traceback
from datetime import datetime, timedelta
from collections import defaultdict

DIR = "/opt/pokemon-monitor-v2"
sys.path.insert(0, DIR)
os.chdir(DIR)

# ============ CONFIG ============
TOTAL_HOURS = 8
ROUND_PAUSE = 120          # seconds between full rounds
SHOP_TIMEOUT = 60          # per-shop timeout
CONCURRENCY = 8            # max simultaneous scrapers
# ================================


def load_all_shops():
    """Load all shop modules from shops/ directory."""
    shops = []
    shops_dir = os.path.join(DIR, "shops")
    for f in sorted(os.listdir(shops_dir)):
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
            print(f"  [LOAD ERROR] {name}: {e}")
    return shops


async def test_one_shop(name, module, sem, timeout=SHOP_TIMEOUT):
    """Test a single shop scraper with timeout."""
    async with sem:
        start = time.time()
        try:
            fn = module.get_products
            if asyncio.iscoroutinefunction(fn):
                prods = await asyncio.wait_for(fn(), timeout=timeout)
            else:
                loop = asyncio.get_running_loop()
                prods = await asyncio.wait_for(
                    loop.run_in_executor(None, fn), timeout=timeout
                )
            elapsed = time.time() - start
            cnt = len(prods) if prods else 0
            avail = len([p for p in prods if p.get("available")]) if prods else 0
            return {
                "name": name, "products": cnt, "available": avail,
                "time": elapsed, "error": None, "status": "OK"
            }
        except asyncio.TimeoutError:
            elapsed = time.time() - start
            return {
                "name": name, "products": 0, "available": 0,
                "time": elapsed, "error": f"TIMEOUT ({timeout}s)", "status": "TIMEOUT"
            }
        except Exception as e:
            elapsed = time.time() - start
            err_short = str(e)[:80]
            return {
                "name": name, "products": 0, "available": 0,
                "time": elapsed, "error": err_short, "status": "ERROR"
            }


async def run_one_round(shops, round_num, sem):
    """Run all scrapers once and return results."""
    print(f"\n{'='*70}")
    print(f"  ROUND #{round_num} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")

    tasks = [test_one_shop(name, mod, sem) for name, mod in shops]
    results = await asyncio.gather(*tasks)

    # Sort by time descending
    results.sort(key=lambda x: -x["time"])

    # Print results
    print(f"\n{'SHOP':<22} {'PROD':>5} {'AVAIL':>5} {'TIME':>7} {'STATUS':<8} ERROR")
    print("-" * 80)
    for r in results:
        flag = "!!!" if r["time"] > 30 else ("!  " if r["time"] > 10 else "   ")
        err = r["error"][:35] if r["error"] else ""
        st_color = r["status"]
        print(f"{flag}{r['name']:<19} {r['products']:>5} {r['available']:>5} {r['time']:>6.1f}s {st_color:<8} {err}")

    # Summary
    ok = [r for r in results if r["status"] == "OK"]
    errs = [r for r in results if r["status"] == "ERROR"]
    timeouts = [r for r in results if r["status"] == "TIMEOUT"]
    zeros = [r for r in results if r["products"] == 0 and r["status"] == "OK"]
    total_prod = sum(r["products"] for r in results)
    total_avail = sum(r["available"] for r in results)

    print(f"\n{'='*70}")
    print(f"  ROUND #{round_num} SUMMARY:")
    print(f"  OK: {len(ok)} | ERRORS: {len(errs)} | TIMEOUTS: {len(timeouts)} | ZERO: {len(zeros)}")
    print(f"  Total products: {total_prod} | Available: {total_avail}")
    print(f"{'='*70}")

    if errs:
        print(f"\n  ERRORS ({len(errs)}):")
        for r in errs:
            print(f"    {r['name']}: {r['error']}")
    if timeouts:
        print(f"\n  TIMEOUTS ({len(timeouts)}):")
        for r in timeouts:
            print(f"    {r['name']} ({r['time']:.0f}s)")

    return results


async def main():
    print("=" * 70)
    print("  POKEMON MONITOR v2 — 8-HOUR ENDURANCE TEST")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Duration: {TOTAL_HOURS} hours | Pause between rounds: {ROUND_PAUSE}s")
    print(f"  Concurrency: {CONCURRENCY} | Timeout per shop: {SHOP_TIMEOUT}s")
    print("=" * 70)

    # Load shops
    shops = load_all_shops()
    print(f"\n  Loaded {len(shops)} shops")
    print(f"  Shops: {', '.join(n for n, _ in shops)}")

    sem = asyncio.Semaphore(CONCURRENCY)
    end_time = datetime.now() + timedelta(hours=TOTAL_HOURS)

    # Track stats across rounds
    all_rounds = []
    shop_stats = defaultdict(lambda: {"ok": 0, "err": 0, "timeout": 0, "total_products": 0, "total_time": 0.0})

    round_num = 0
    while datetime.now() < end_time:
        round_num += 1
        remaining = end_time - datetime.now()
        print(f"\n  Time remaining: {str(remaining).split('.')[0]}")

        results = await run_one_round(shops, round_num, sem)
        all_rounds.append(results)

        # Update per-shop stats
        for r in results:
            s = shop_stats[r["name"]]
            if r["status"] == "OK":
                s["ok"] += 1
            elif r["status"] == "ERROR":
                s["err"] += 1
            else:
                s["timeout"] += 1
            s["total_products"] += r["products"]
            s["total_time"] += r["time"]

        # Check if time left for another round
        if datetime.now() + timedelta(seconds=ROUND_PAUSE) >= end_time:
            break

        print(f"\n  Sleeping {ROUND_PAUSE}s before next round...")
        await asyncio.sleep(ROUND_PAUSE)

    # ============ FINAL SUMMARY ============
    print("\n\n")
    print("=" * 70)
    print("  FINAL SUMMARY — 8-HOUR ENDURANCE TEST")
    print(f"  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Total rounds: {round_num}")
    print("=" * 70)

    # Sort by reliability (error rate)
    sorted_shops = sorted(shop_stats.items(), key=lambda x: x[1]["err"] + x[1]["timeout"], reverse=True)

    print(f"\n{'SHOP':<22} {'OK':>4} {'ERR':>4} {'TMO':>4} {'RATE':>6} {'AVG_T':>6} {'AVG_P':>6}")
    print("-" * 70)
    for name, s in sorted_shops:
        total_runs = s["ok"] + s["err"] + s["timeout"]
        rate = f"{s['ok']/total_runs*100:.0f}%" if total_runs > 0 else "N/A"
        avg_t = f"{s['total_time']/total_runs:.1f}s" if total_runs > 0 else "N/A"
        avg_p = f"{s['total_products']/total_runs:.0f}" if total_runs > 0 else "N/A"
        flag = "X " if s["err"] + s["timeout"] > round_num * 0.5 else "  "
        print(f"{flag}{name:<20} {s['ok']:>4} {s['err']:>4} {s['timeout']:>4} {rate:>6} {avg_t:>6} {avg_p:>6}")

    # Problem shops
    problem_shops = [(n, s) for n, s in sorted_shops if s["err"] + s["timeout"] > round_num * 0.3]
    if problem_shops:
        print(f"\n  PROBLEM SHOPS (>30% failure rate):")
        for name, s in problem_shops:
            total_runs = s["ok"] + s["err"] + s["timeout"]
            print(f"    {name}: {s['err']} errors, {s['timeout']} timeouts out of {total_runs} runs")

    # Perfect shops
    perfect = [(n, s) for n, s in sorted_shops if s["err"] == 0 and s["timeout"] == 0]
    print(f"\n  PERFECT SHOPS (0 errors): {len(perfect)}/{len(shop_stats)}")

    # Overall stats
    total_ok = sum(s["ok"] for s in shop_stats.values())
    total_err = sum(s["err"] for s in shop_stats.values())
    total_tmo = sum(s["timeout"] for s in shop_stats.values())
    total_all = total_ok + total_err + total_tmo
    print(f"\n  OVERALL: {total_ok}/{total_all} successful ({total_ok/total_all*100:.1f}%)")
    print(f"  Errors: {total_err} | Timeouts: {total_tmo}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
