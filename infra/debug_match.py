#!/usr/bin/env python3
"""Debug why fuzzy match fails on VPS."""
import asyncio, sys, os, re
sys.path.insert(0, "/opt/pokemon-monitor-v2")
os.chdir("/opt/pokemon-monitor-v2")

import aiohttp
from price_compare import _load_sitemap, match_set_number, _normalize_name, STOP_WORDS, HEADERS

async def main():
    async with aiohttp.ClientSession(headers=HEADERS) as s:
        sitemap = await _load_sitemap(s)
    print(f"Sitemap: {len(sitemap)} sets")
    
    test_names = [
        "LEGO® Icons: Polaroid OneStep SX-70 - 18+",
        "LEGO® Star Wars™: 501st Clone Troopers™ Battle Pack - 6+",
        "LEGO® Technic: Koenigsegg Jesko Absolut w kolorze szarym - 10+",
        "LEGO® Icons: Chrysanthemum - 18+",
        "LEGO® Creator: Daffodils - 8+",
    ]
    
    # Check slug for known set
    print(f"\nSlug for 75345: '{sitemap.get('75345', 'NOT FOUND')}'")
    print(f"Slug for 21345: '{sitemap.get('21345', 'NOT FOUND')}'")
    print(f"Slug for 42173: '{sitemap.get('42173', 'NOT FOUND')}'")
    print()
    
    for name in test_names:
        words = _normalize_name(name)
        result = match_set_number(name, sitemap)
        
        # Manual check - find best match
        best_num = None
        best_score = 0
        best_slug = ""
        for num, slug in sitemap.items():
            slug_words = set(slug.split('-')) - STOP_WORDS
            slug_words = {w for w in slug_words if len(w) > 1}
            score = len(words & slug_words)
            if score > best_score:
                best_score = score
                best_num = num
                best_slug = slug
        
        print(f"NAME: {name}")
        print(f"  normalized words: {sorted(words)}")
        print(f"  match result: {result}")
        print(f"  best: #{best_num} score={best_score} slug='{best_slug[:60]}'")
        if best_num:
            slug_words = set(best_slug.split('-')) - STOP_WORDS
            slug_words = {w for w in slug_words if len(w) > 1}
            common = words & slug_words
            print(f"  slug words: {sorted(slug_words)[:10]}")
            print(f"  COMMON: {common}")
        print()

asyncio.run(main())
