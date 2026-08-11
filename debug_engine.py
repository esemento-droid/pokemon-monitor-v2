#!/usr/bin/env python3
"""Debug: what does tcgumisia.pl return to the engine?"""
import asyncio
import aiohttp

async def test():
    jar = aiohttp.CookieJar(unsafe=True)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"}
    async with aiohttp.ClientSession(headers=headers, cookie_jar=jar) as session:
        # First request - check for PoW
        async with session.get("https://tcgumisia.pl/pokemon") as resp:
            html = await resp.text()
            print(f"Status: {resp.status}")
            print(f"HTML length: {len(html)}")
            print(f"Has 'Weryfikacja': {'Weryfikacja' in html}")
            print(f"Has 'nodea': {'nodea' in html}")
            print(f"Has 'c-product-box': {html.count('c-product-box')}")
            print(f"Has 'c-product-box__title': {html.count('c-product-box__title')}")
            print(f"Has 'Dostepny': {html.count('Dostępny')}")
            print(f"Has 'Niedostepny': {html.count('Niedostępny')}")
            print()
            print("=== FIRST 1000 CHARS ===")
            print(html[:1000])
            print()
            print("=== SEARCHING FOR PRODUCT PATTERN ===")
            # Look for the split pattern used by engine
            chunks = html.split('c-product-box"')
            print(f"Split by 'c-product-box\"' gives {len(chunks)} chunks")
            if len(chunks) > 1:
                print(f"First product chunk (500 chars):")
                print(chunks[1][:500])

asyncio.run(test())
