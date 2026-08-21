#!/usr/bin/env python3
"""Diagnostic: fetch battlestash HTML via CF solver and analyze structure."""
import asyncio
import aiohttp
from bs4 import BeautifulSoup

URL = "https://battlestash.pl/kategoria/gry-karciane/pokemon-tcg/"
FLARESOLVERR = "http://localhost:8191/v1"


async def main():
    print(f"[DIAG] Fetching {URL} via CF solver...")
    async with aiohttp.ClientSession() as s:
        payload = {"cmd": "request.get", "url": URL, "maxTimeout": 90000}
        async with s.post(FLARESOLVERR, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as r:
            d = await r.json()

    html = d.get("solution", {}).get("response", "")
    print(f"[DIAG] Status: {d.get('status')} | HTML length: {len(html)}")

    if not html or len(html) < 1000:
        print("[DIAG] EMPTY RESPONSE - CF solver failed")
        return

    soup = BeautifulSoup(html, "html.parser")

    # Check title
    title = soup.title.get_text(strip=True) if soup.title else "NO TITLE"
    print(f"[DIAG] Page title: {title}")

    # Check if CF challenge page
    if "moment" in title.lower() or "checking" in title.lower():
        print("[DIAG] STILL ON CF CHALLENGE PAGE!")
        return

    # Try various product selectors
    selectors = [
        ("li.product", soup.select("li.product")),
        (".product-miniature", soup.select(".product-miniature")),
        (".products .product", soup.select(".products .product")),
        ("[class*='product']", soup.select("[class*='product']")),
        ("article.product", soup.select("article.product")),
        (".woocommerce-loop-product__title", soup.select(".woocommerce-loop-product__title")),
        ("h2.wc-block-grid__product-title", soup.select("h2.wc-block-grid__product-title")),
        (".wc-block-grid__product", soup.select(".wc-block-grid__product")),
        ("[data-product_id]", soup.select("[data-product_id]")),
        (".product-item", soup.select(".product-item")),
        (".product-card", soup.select(".product-card")),
        (".product-loop", soup.select(".product-loop")),
    ]

    print(f"\n[DIAG] === SELECTOR RESULTS ===")
    for name, els in selectors:
        if els:
            print(f"  {name}: {len(els)} elements")
            # Show first element's classes and tag
            first = els[0]
            print(f"    First: <{first.name} class='{' '.join(first.get('class', []))}'>")
            # Show text content preview
            text = first.get_text(strip=True)[:150]
            print(f"    Text: {text}")
        else:
            print(f"  {name}: 0")

    # Show all classes containing 'product' anywhere on page
    print(f"\n[DIAG] === CLASSES WITH 'product' (first 30) ===")
    all_product_classes = set()
    for el in soup.select("[class]"):
        for cls in el.get("class", []):
            if "product" in cls.lower():
                all_product_classes.add(cls)
    for cls in sorted(all_product_classes)[:30]:
        print(f"  .{cls}")

    # Show page structure around products
    print(f"\n[DIAG] === UL/OL with 'product' class ===")
    for ul in soup.select("ul[class*='product'], ol[class*='product']"):
        print(f"  <{ul.name} class='{' '.join(ul.get('class', []))}'>: {len(ul.find_all('li'))} items")

    # Show first 3000 chars of body text (to understand page structure)
    body = soup.body
    if body:
        text = body.get_text(separator="\n", strip=True)
        lines = [l for l in text.split("\n") if l.strip()]
        print(f"\n[DIAG] === PAGE TEXT (first 50 non-empty lines) ===")
        for line in lines[:50]:
            print(f"  {line[:120]}")

    # Show raw HTML snippet around product area (search for price pattern)
    import re
    price_matches = re.findall(r'(\d+[.,]\d+)\s*zł', html)
    print(f"\n[DIAG] === PRICES FOUND (zł pattern): {len(price_matches)} ===")
    for p in price_matches[:10]:
        print(f"  {p} zł")

    # Find the HTML around first price
    if price_matches:
        idx = html.find(price_matches[0] + ",")
        if idx == -1:
            idx = html.find(price_matches[0])
        if idx > 0:
            snippet = html[max(0, idx-500):idx+200]
            print(f"\n[DIAG] === HTML SNIPPET AROUND FIRST PRICE ===")
            print(snippet[:1000])


if __name__ == "__main__":
    asyncio.run(main())
