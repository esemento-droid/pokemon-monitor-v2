#!/usr/bin/env python3
"""Build price cache — fetch promoklocki prices for limango LEGO sets.
Uses klockoradar sitemap + limango live scan to find set numbers, then fetches prices."""
import asyncio
import sys
import os
import re
import json
import time
import ssl
import aiohttp

sys.path.insert(0, "/opt/pokemon-monitor-v2")
os.chdir("/opt/pokemon-monitor-v2")

PROMOKLOCKI_BASE = "https://promoklocki.pl"
FLARESOLVERR_URL = "http://localhost:8191/v1"
CACHE_FILE = "/opt/pokemon-monitor-v2/data/price_cache.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
SITEMAP_URLS = [f"https://klockoradar.pl/sitemap/{i}.xml" for i in range(8)]
STOP_WORDS = {'lego', 'the', 'and', 'with', 'in', 'of', 'for', 'to', 'a', 'an', 'w', 'i', 'z', 'do', 'na', 'od', 'dla', 'set', 'r', 'from'}

LIMANGO_BASE = "https://www.limango.pl"
LIMANGO_URL = f"{LIMANGO_BASE}/shop/lego"
NEXT_DATA_RE = re.compile(r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

PRICE_RE = re.compile(r'"lowPrice"\s*:\s*"?([\d.,]+)"?', re.IGNORECASE)


def normalize(name):
    name = name.lower().replace("\u00ae", "").replace("(r)", "").replace("\u2122", "")
    name = re.sub(r'[^a-z0-9\s]', ' ', name)
    words = set(name.split()) - STOP_WORDS
    return {w for w in words if len(w) > 1}


def match_to_sitemap(product_name, sitemap):
    name_words = normalize(product_name)
    if not name_words:
        return None
    best_num = None
    best_score = 0
    for num, slug in sitemap.items():
        slug_words = set(slug.split('-')) - STOP_WORDS
        slug_words = {w for w in slug_words if len(w) > 1}
        score = len(name_words & slug_words)
        if score > best_score:
            best_score = score
            best_num = num
    if best_score >= 2:
        return best_num
    if best_score == 1:
        slug = sitemap.get(best_num, '')
        matching = name_words & set(slug.split('-'))
        for w in matching:
            if len(w) >= 8:
                return best_num
    return None


async def main():
    print("=== BUILD PRICE CACHE ===")
    print()

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Step 1: Load klockoradar sitemap
        print("1. Loading klockoradar sitemap...")
        sitemap = {}
        for url in SITEMAP_URLS:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        xml = await resp.text()
                        for m in re.findall(r'klockoradar\.pl/sets/(\d+)-([^<]+)</loc>', xml):
                            sitemap[m[0]] = m[1]
            except:
                pass
        print(f"   Loaded {len(sitemap)} sets")

        # Step 2: Fetch limango products and match to set numbers
        print("2. Fetching limango LEGO products...")
        set_numbers = {}  # num → product name
        for page in range(1, 7):
            url = f"{LIMANGO_URL}?page={page}" if page > 1 else LIMANGO_URL
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30), ssl=ssl_ctx) as resp:
                    html = await resp.text()
                match = NEXT_DATA_RE.search(html)
                if not match:
                    break
                data = json.loads(match.group(1))
                products = data["props"]["pageProps"]["preloadedState"]["listing"]["products"]["data"]
                for item in products:
                    name = item.get("name", "")
                    if not name:
                        continue
                    # Direct number extraction
                    m = re.search(r'\b(\d{5})\b', name)
                    if m:
                        set_numbers[m.group(1)] = name
                    else:
                        # Fuzzy match
                        num = match_to_sitemap(name, sitemap)
                        if num:
                            set_numbers[num] = name
                if len(products) < 50:
                    break
            except Exception as e:
                print(f"   Page {page} error: {e}")
                break
        print(f"   Matched {len(set_numbers)} products to set numbers")
        print()

        # Step 3: Fetch promoklocki prices
        # Strategy: try direct HTTP first (JSON-LD lowPrice in raw HTML), FS only as fallback
        print("3. Fetching promoklocki prices...")

        cache = {}
        for i, (num, name) in enumerate(sorted(set_numbers.items())):
            url = f"{PROMOKLOCKI_BASE}/{num}"
            price = None

            # Try 1: Direct HTTP (no FS — works if promoklocki serves lowPrice in HTML without JS)
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15), ssl=ssl_ctx, allow_redirects=True) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        m = PRICE_RE.search(html)
                        if m:
                            price = float(m.group(1).replace(",", ".").replace(" ", ""))
            except:
                pass

            # Try 2: FlareSolverr (if direct failed — CF blocked)
            if not price:
                try:
                    payload = {"cmd": "request.get", "url": url, "maxTimeout": 30000}
                    async with session.post(FLARESOLVERR_URL, json=payload, timeout=aiohttp.ClientTimeout(total=40)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("status") == "ok":
                                fs_html = data.get("solution", {}).get("response", "")
                                if fs_html:
                                    m = PRICE_RE.search(fs_html)
                                    if m:
                                        price = float(m.group(1).replace(",", ".").replace(" ", ""))
                except:
                    pass

            if price and price > 0:
                cache[num] = {
                    "set_number": num,
                    "lowest_price": price,
                    "promoklocki_url": url,
                    "product_name": name[:80],
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "updated_at_ts": time.time(),
                }
                print(f"   [{i+1}/{len(set_numbers)}] #{num}: {price:.2f} zl — {name[:50]}")
            else:
                print(f"   [{i+1}/{len(set_numbers)}] #{num}: NO PRICE")

            await asyncio.sleep(3)

    # Save cache
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    print(f"\n=== DONE: {len(cache)} prices saved to {CACHE_FILE} ===")

asyncio.run(main())
