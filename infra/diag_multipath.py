#!/usr/bin/env python3
"""
Multi-path diagnostic: test VPS direct vs Proxy for CF and non-CF shops.
Tests connectivity, latency, and CF challenge status.
"""
import asyncio
import time
import aiohttp

PROXY_HTTP = "http://127.0.0.1:8888"
PROXY_TAILSCALE = "http://100.127.72.24:8888"

# CF-protected shops (need solver)
CF_TARGETS = {
    "gralnia": "https://gralnia.org/?s=pokemon+tcg&post_type=product",
    "xjoy": "https://www.xjoy.pl/278-pokemon-tcg",
    "battlestash": "https://battlestash.pl/wp-json/wc/store/v1/products?category=83&per_page=20",
    "dystryktzero": "https://dystryktzero.pl/kategoria-produktu/pokemon-tcg/",
    "sklepkleks": "https://sklepkleks.pl/kategoria-produktu/pokemon-tcg/",
}

# Non-CF shops (direct aiohttp, should always work)
DIRECT_TARGETS = {
    "maginarium": "https://maginarium.pl/?s=Pokemon+tcg+&post_type=product",
    "monsteriada": "https://monsteriada.pl/93-pokemon-tcg-karty-kolekjonerskie",
    "strefamtg": "https://strefamtg.pl/2838-talie-i-zestawy-kart-pokemon",
    "am76": "https://am76.pl/szukaj?search_query=pokemon+tcg",
}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


async def test_url(session, label, url, proxy=None):
    """Test a single URL, return (label, status, time, body_len, cf_challenge)."""
    t0 = time.time()
    try:
        async with session.get(
            url,
            proxy=proxy,
            headers={"User-Agent": UA},
            timeout=aiohttp.ClientTimeout(total=15),
            ssl=False,
        ) as resp:
            body = await resp.text()
            elapsed = time.time() - t0
            cf = "just a moment" in body.lower() or "checking your browser" in body.lower()
            return (label, resp.status, elapsed, len(body), cf)
    except Exception as e:
        elapsed = time.time() - t0
        return (label, f"ERR: {str(e)[:60]}", elapsed, 0, False)


async def main():
    print("=" * 70)
    print("  MULTI-PATH CONNECTIVITY DIAGNOSTIC")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        # === TEST 1: Non-CF shops (VPS direct — no proxy) ===
        print("\n--- 1. NON-CF SHOPS (VPS direct, no proxy) ---")
        print(f"{'Shop':<16} {'Status':<8} {'Time':<8} {'Size':<8} {'CF?'}")
        tasks = [test_url(session, name, url) for name, url in DIRECT_TARGETS.items()]
        results = await asyncio.gather(*tasks)
        for label, status, elapsed, size, cf in results:
            print(f"  {label:<14} {str(status):<8} {elapsed:.2f}s   {size:<8} {'YES!' if cf else 'no'}")

        # === TEST 2: Non-CF shops (via mobile proxy) ===
        print("\n--- 2. NON-CF SHOPS (via proxy 127.0.0.1:8888) ---")
        print(f"{'Shop':<16} {'Status':<8} {'Time':<8} {'Size':<8} {'CF?'}")
        tasks = [test_url(session, name, url, proxy=PROXY_HTTP) for name, url in DIRECT_TARGETS.items()]
        results = await asyncio.gather(*tasks)
        for label, status, elapsed, size, cf in results:
            print(f"  {label:<14} {str(status):<8} {elapsed:.2f}s   {size:<8} {'YES!' if cf else 'no'}")

        # === TEST 3: CF shops (VPS direct — will get CF challenge but shows connectivity) ===
        print("\n--- 3. CF SHOPS (VPS direct — expect CF challenge) ---")
        print(f"{'Shop':<16} {'Status':<8} {'Time':<8} {'Size':<8} {'CF?'}")
        tasks = [test_url(session, name, url) for name, url in CF_TARGETS.items()]
        results = await asyncio.gather(*tasks)
        for label, status, elapsed, size, cf in results:
            print(f"  {label:<14} {str(status):<8} {elapsed:.2f}s   {size:<8} {'YES!' if cf else 'no'}")

        # === TEST 4: CF shops (via mobile proxy) ===
        print("\n--- 4. CF SHOPS (via proxy 127.0.0.1:8888) ---")
        print(f"{'Shop':<16} {'Status':<8} {'Time':<8} {'Size':<8} {'CF?'}")
        tasks = [test_url(session, name, url, proxy=PROXY_HTTP) for name, url in CF_TARGETS.items()]
        results = await asyncio.gather(*tasks)
        for label, status, elapsed, size, cf in results:
            print(f"  {label:<14} {str(status):<8} {elapsed:.2f}s   {size:<8} {'YES!' if cf else 'no'}")

        # === TEST 5: Tailscale direct proxy (bypasses tunnel) ===
        print("\n--- 5. CF SHOPS (via Tailscale 100.127.72.24:8888) ---")
        print(f"{'Shop':<16} {'Status':<8} {'Time':<8} {'Size':<8} {'CF?'}")
        tasks = [test_url(session, name, url, proxy=PROXY_TAILSCALE) for name, url in CF_TARGETS.items()]
        results = await asyncio.gather(*tasks)
        for label, status, elapsed, size, cf in results:
            print(f"  {label:<14} {str(status):<8} {elapsed:.2f}s   {size:<8} {'YES!' if cf else 'no'}")

        # === TEST 6: CF Bridge live test ===
        print("\n--- 6. CF BRIDGE SOLVE TEST (gralnia via localhost:8191) ---")
        t0 = time.time()
        try:
            payload = {
                "cmd": "request.get",
                "url": "https://gralnia.org/?s=pokemon+tcg&post_type=product",
                "maxTimeout": 30000,
            }
            async with session.post(
                "http://127.0.0.1:8191/v1",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=45),
            ) as resp:
                data = await resp.json()
                elapsed = time.time() - t0
                status = data.get("status")
                html = data.get("solution", {}).get("response", "")
                print(f"  Status: {status} | Time: {elapsed:.1f}s | HTML: {len(html)} chars")
                if status != "ok":
                    print(f"  Error: {data.get('message', 'unknown')}")
                elif html:
                    has_products = "product" in html.lower() and ("pokemon" in html.lower() or "woocommerce" in html.lower())
                    print(f"  Products in HTML: {'YES' if has_products else 'NO (challenge page?)'}")
        except Exception as e:
            print(f"  CF Bridge ERROR: {e}")

    print("\n" + "=" * 70)
    print("  VERDICT:")
    print("=" * 70)
    print("  If TEST 1 fails → VPS outbound broken")
    print("  If TEST 1 OK but TEST 2 fails → mobile proxy broken")
    print("  If TEST 3 shows CF but TEST 4 also CF → mobile IP also CF-challenged")
    print("  If TEST 6 fails → CF solver browser can't beat challenge (fingerprint ban)")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
