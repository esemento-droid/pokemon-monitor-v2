#!/usr/bin/env python3
"""Debug: test engine parsing on live tcgumisia.pl"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aiohttp
import re

EXCLUDE_KEYWORDS = [
    "lorcana", "one piece", "flesh and blood", "fab", "disney",
    "album", "sleeve", "koszulk", "toploader", "ultra pro",
    "ochraniacz", "plastikowy", "jpn", "(jpn", "pencil",
    "riftbound", "cyberpunk", "playmat", "mata", "singiel", "single",
    "deck box", "figurk", "plusz", "portfolio",
]

async def test():
    jar = aiohttp.CookieJar(unsafe=True)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"}
    async with aiohttp.ClientSession(headers=headers, cookie_jar=jar) as session:
        async with session.get("https://tcgumisia.pl/pokemon") as resp:
            html = await resp.text()
            print(f"Status: {resp.status}")
            print(f"HTML length: {len(html)}")
            print(f"Has 'Weryfikacja': {'Weryfikacja' in html}")
            print()

            # Split by product box class
            chunks = re.split(r'class="[^"]*\bc-product-box\b(?![-_])[^"]*"', html)
            print(f"Split = {len(chunks)-1} raw product boxes")

            products = []
            for chunk in chunks[1:]:
                chunk = chunk[:5000]

                # Title
                title_match = re.search(r'c-product-box__title[^>]*>([^<]+)<', chunk)
                if not title_match:
                    continue
                name = title_match.group(1).strip()
                if not name or len(name) < 3:
                    continue

                # Exclude
                if any(kw in name.lower() for kw in EXCLUDE_KEYWORDS):
                    continue

                # Link — skip koszyk
                href = "NO LINK"
                for m in re.finditer(r'<a[^>]*href="(https://tcgumisia\.pl/[^"]*?)"[^>]*>', chunk):
                    if "koszyk" not in m.group(1) and len(m.group(1)) > 30:
                        href = m.group(1)
                        break

                # Availability
                available = not ("c-avaibility--none" in chunk or "Niedostępny" in chunk)

                # Price
                price_match = re.search(r'c-product-box__price-value[^>]*>\s*([\d\s,.]+)', chunk)
                price = price_match.group(1).strip() if price_match else "?"

                products.append((name, href, available, price))

            print(f"After filtering: {len(products)} products")
            print()
            avail = [p for p in products if p[2]]
            unavail = [p for p in products if not p[2]]
            print(f"  AVAILABLE: {len(avail)}")
            print(f"  SOLD OUT: {len(unavail)}")
            print()
            print("--- AVAILABLE ---")
            for name, href, _, price in avail[:20]:
                print(f"  {price:>8} PLN | {name[:55]}")
                print(f"             {href[:70]}")
            print()
            print("--- SOLD OUT (first 10) ---")
            for name, href, _, price in unavail[:10]:
                print(f"  {price:>8} PLN | {name[:55]}")
                print(f"             {href[:70]}")

asyncio.run(test())
