#!/usr/bin/env python3
"""Diagnostyka smyk v3 — pełny HTML jednego produktu + img + availability"""
import asyncio
import aiohttp
from bs4 import BeautifulSoup

URL = "https://www.smyk.com/pl/pl/search?q=Pokemon%20tcg"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept-Language": "pl-PL,pl;q=0.9",
}

async def main():
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            html = await resp.text()

    soup = BeautifulSoup(html, "lxml")
    items = soup.select(".complex-product")
    print(f"Total items: {len(items)}\n")

    # Show full HTML of first 3 products (name, img, price, availability)
    for i, item in enumerate(items[:3]):
        print(f"{'='*60}")
        print(f"PRODUCT #{i+1}")
        print(f"{'='*60}")
        
        # Name
        name_tag = item.select_one(".complex-product__name")
        name = name_tag.get_text(" ", strip=True) if name_tag else "NO NAME"
        print(f"Name: {name}")
        
        # Link
        link = None
        for a in item.select("a[href]"):
            h = a.get("href", "")
            if "/p/" in h or "/i" in h:
                link = h
                break
        print(f"Link: {link}")
        
        # Price
        price_tag = item.select_one(".complex-product__price")
        price = price_tag.get_text(" ", strip=True) if price_tag else "NO PRICE"
        print(f"Price: {price}")
        
        # ALL images in this product
        imgs = item.find_all("img")
        print(f"Images ({len(imgs)}):")
        for img in imgs:
            for attr in ("data-srcset", "data-src", "srcset", "src", "lazy-src"):
                val = img.get(attr, "")
                if val:
                    print(f"  {attr}: {val[:150]}")
        
        # Availability - check for button/text
        text_low = item.get_text(" ", strip=True).lower()
        has_dodaj = "dodaj do koszyka" in text_low
        has_brak = "niedost" in text_low or "brak" in text_low or "wyprzed" in text_low
        print(f"Has 'dodaj do koszyka': {has_dodaj}")
        print(f"Has 'niedost/brak/wyprzed': {has_brak}")
        
        # Button
        buttons = item.select("button")
        for btn in buttons:
            btn_text = btn.get_text(strip=True)
            if btn_text and len(btn_text) > 2:
                print(f"  Button: '{btn_text}' | class={btn.get('class','')}")
        
        # Full raw HTML (first 2000 chars)
        raw = str(item)
        print(f"\nRAW HTML ({len(raw)} chars, showing 2500):")
        print(raw[:2500])
        print()

asyncio.run(main())
