#!/usr/bin/env python3
"""Diagnostic: fetch xjoy HTML via CF solver and analyze structure."""
import asyncio
import aiohttp
import json
from bs4 import BeautifulSoup

URL = "https://www.xjoy.pl/278-pokemon-tcg"
FS = "http://localhost:8191/v1"

async def main():
    print(f"[DIAG] Fetching {URL}...")
    async with aiohttp.ClientSession() as s:
        r = await s.post(FS, json={"cmd": "request.get", "url": URL, "maxTimeout": 90000}, timeout=aiohttp.ClientTimeout(total=120))
        d = await r.json()
    h = d.get("solution", {}).get("response", "")
    if not h:
        print(f"EMPTY: {d.get('status')} {d.get('message','')}")
        return
    open("/tmp/xjoy_debug.html", "w").write(h)
    print(f"SAVED {len(h)} chars")
    soup = BeautifulSoup(h, "html.parser")
    print(f"Title: {soup.title.get_text(strip=True) if soup.title else 'none'}")
    for sel in [".product-miniature", "article.product-miniature", "li.product", ".product-small", ".product-container"]:
        els = soup.select(sel)
        if els:
            print(f"\n{sel}: {len(els)} products")
            print("=== FIRST PRODUCT ===")
            print(str(els[0])[:2000])
            print("=== SECOND PRODUCT ===")
            if len(els) > 1:
                print(str(els[1])[:2000])
            break
    else:
        print("NO PRODUCTS FOUND with standard selectors")
        for t in soup.select("[class]")[:20]:
            cls = " ".join(t.get("class", []))
            if "product" in cls.lower():
                print(f"  <{t.name} class='{cls[:80]}'>")

if __name__ == "__main__":
    asyncio.run(main())
