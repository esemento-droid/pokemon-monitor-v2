#!/usr/bin/env python3
"""Debug: what does tcgumisia.pl return to the engine?"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aiohttp
import re

async def test():
    jar = aiohttp.CookieJar(unsafe=True)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"}
    async with aiohttp.ClientSession(headers=headers, cookie_jar=jar) as session:
        async with session.get("https://tcgumisia.pl/pokemon") as resp:
            html = await resp.text()
            print(f"Status: {resp.status}")
            print(f"HTML length: {len(html)}")
            print(f"Has 'Weryfikacja': {'Weryfikacja' in html}")
            print(f"Has 'c-product-box__title': {html.count('c-product-box__title')}")
            print()

            # Test the new split approach
            chunks = html.split('c-product-box__title')
            print(f"Split by 'c-product-box__title' = {len(chunks)} chunks ({len(chunks)-1} products)")
            print()

            # Parse first 3 products
            count = 0
            for chunk in chunks[1:]:
                chunk = chunk[:4000]
                title_match = re.search(r'[^>]*>([^<]+)<', chunk)
                if not title_match:
                    continue
                name = title_match.group(1).strip()
                if not name or len(name) < 3:
                    continue

                # Link
                link_match = re.search(r'<a[^>]*href="(https://tcgumisia\.pl/[^"]*?)"[^>]*>', chunk)
                href = link_match.group(1) if link_match else "NO LINK"

                # Availability
                available = True
                if "c-avaibility--none" in chunk or "Niedostępny" in chunk:
                    available = False

                # Price
                price_match = re.search(r'c-product-box__price-value[^>]*>\s*([\d\s,.]+)', chunk)
                price = price_match.group(1).strip() if price_match else "NO PRICE"

                count += 1
                status = "AVAIL" if available else "---"
                print(f"  [{status:5}] {price:>10} PLN | {name[:60]}")
                print(f"          URL: {href[:80]}")

                if count >= 10:
                    break

            print(f"\n  ... showed {count} of {len(chunks)-1} products")

asyncio.run(test())
