#!/usr/bin/env python3
"""Diagnostyka smyk v2 — pełny HTML dump + szukaj Destined Rivals"""
import asyncio
import aiohttp

URLS = [
    "https://www.smyk.com/pl/pl/search?q=Pokemon%20tcg",
    "https://www.smyk.com/pl/pl/search?q=Pokemon",
    "https://www.smyk.com/pl/pl/search?q=Pokemon+Destined+Rivals",
    "https://www.smyk.com/pl/pl/search?q=pokemon+booster",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept-Language": "pl-PL,pl;q=0.9",
}

async def main():
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for url in URLS:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    html = await resp.text()
                    # Count products
                    count = html.count("complex-product")
                    has_destined = "destined" in html.lower() or "rivals" in html.lower()
                    has_dodaj = "dodaj do koszyka" in html.lower()
                    has_niedost = "niedost" in html.lower() or "brak" in html.lower()
                    
                    # Find all image patterns
                    import re
                    imgs = re.findall(r'(https://img\.smyk\.com[^"\'>\s]+)', html)
                    
                    print(f"\n{'='*60}")
                    print(f"URL: {url}")
                    print(f"Status: {resp.status} | HTML size: {len(html)}")
                    print(f"Products (.complex-product): {count}")
                    print(f"Has 'Destined/Rivals': {has_destined}")
                    print(f"Has 'dodaj do koszyka': {has_dodaj}")
                    print(f"Has 'niedost/brak': {has_niedost}")
                    print(f"Images found: {len(imgs)}")
                    if imgs:
                        print(f"  Sample img: {imgs[0][:120]}")
                    
                    # Show first product block
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, "lxml")
                    items = soup.select(".complex-product")
                    if items:
                        first = items[0]
                        print(f"\nFirst product HTML (trimmed):")
                        print(str(first)[:1500])
                    else:
                        # Maybe different class?
                        print(f"\nNo .complex-product found. Trying other selectors...")
                        for sel in [".product-card", ".product-item", "[data-product]", ".product-tile", "article"]:
                            found = soup.select(sel)
                            if found:
                                print(f"  Found {len(found)} with '{sel}'")
                                print(f"  First: {str(found[0])[:500]}")
                                break
                        else:
                            # Dump first 3000 chars of body
                            body = soup.find("body")
                            if body:
                                print(f"\nBody text (first 2000):")
                                print(body.get_text(" ", strip=True)[:2000])
            except Exception as e:
                print(f"\nERROR for {url}: {e}")

asyncio.run(main())
