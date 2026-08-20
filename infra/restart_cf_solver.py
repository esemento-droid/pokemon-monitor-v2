#!/usr/bin/env python3
"""
Quick CF solver health test after deploy.
Attempts one solve via CF Bridge, reports result.
Run on VPS after restart to verify CF solver works.
"""
import asyncio
import aiohttp
import time
import sys

TARGETS = {
    "gralnia": "https://gralnia.org/?s=pokemon+tcg&post_type=product",
    "xjoy": "https://www.xjoy.pl/278-pokemon-tcg",
    "sklepkleks": "https://sklepkleks.pl/kategoria-produktu/pokemon-tcg/",
    "maginarium_proxy": "https://maginarium.pl/?s=Pokemon+tcg+&post_type=product",
}


async def test_cf_bridge(name, url):
    """Test single URL via CF Bridge (localhost:8191)."""
    payload = {"cmd": "request.get", "url": url, "maxTimeout": 45000}
    t0 = time.time()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://127.0.0.1:8191/v1",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=55),
            ) as resp:
                data = await resp.json()
                elapsed = time.time() - t0
                status = data.get("status")
                html = data.get("solution", {}).get("response", "")
                has_products = len(html) > 5000 and ("product" in html.lower())
                return f"  {name:<18} {status:<6} {elapsed:.1f}s  HTML={len(html):>7}  Products={'YES' if has_products else 'NO'}"
    except Exception as e:
        elapsed = time.time() - t0
        return f"  {name:<18} ERROR  {elapsed:.1f}s  {str(e)[:50]}"


async def test_direct_proxy(name, url):
    """Test URL directly via mobile proxy (no CF solver)."""
    t0 = time.time()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                proxy="http://127.0.0.1:8888",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                body = await resp.text()
                elapsed = time.time() - t0
                cf = "just a moment" in body.lower()
                return f"  {name:<18} {resp.status:<6} {elapsed:.1f}s  Size={len(body):>7}  CF={'YES' if cf else 'no'}"
    except Exception as e:
        elapsed = time.time() - t0
        return f"  {name:<18} ERROR  {elapsed:.1f}s  {str(e)[:50]}"


async def main():
    print("=" * 60)
    print("  CF SOLVER HEALTH CHECK")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Test 1: Direct proxy (non-CF shops)
    print("\n--- Direct proxy test (non-CF shops) ---")
    results = await asyncio.gather(
        test_direct_proxy("maginarium", "https://maginarium.pl/?s=Pokemon+tcg+&post_type=product"),
        test_direct_proxy("monsteriada", "https://monsteriada.pl/93-pokemon-tcg-karty-kolekjonerskie"),
        test_direct_proxy("strefamtg", "https://strefamtg.pl/2838-talie-i-zestawy-kart-pokemon"),
    )
    for r in results:
        print(r)

    # Test 2: CF Bridge (CF shops)
    print("\n--- CF Bridge solve test (sequential) ---")
    for name, url in TARGETS.items():
        if "proxy" in name:
            continue
        result = await test_cf_bridge(name, url)
        print(result)

    print("\n" + "=" * 60)
    print("  If direct proxy = 200 → non-CF fix works")
    print("  If CF Bridge = ok + Products=YES → CF solver works")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
