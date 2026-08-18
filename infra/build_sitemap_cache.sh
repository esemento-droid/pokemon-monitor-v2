#!/bin/bash
# Buduje sitemap_cache.json jednorazowo (klockoradar sitemap -> plik JSON)
# bash infra/build_sitemap_cache.sh | curl -sF 'file=@-' https://paste.rs

cd /opt/pokemon-monitor-v2

echo "=== BUILD SITEMAP CACHE ==="
echo "Data: $(date)"

./venv/bin/python3 -c "
import asyncio, json, sys
sys.path.insert(0, '.')
from price_compare import _load_sitemap, HEADERS
import aiohttp

async def build():
    async with aiohttp.ClientSession(headers=HEADERS) as s:
        sitemap = await _load_sitemap(s)
        if sitemap:
            with open('data/sitemap_cache.json', 'w') as f:
                json.dump(sitemap, f, ensure_ascii=False)
            print(f'OK: {len(sitemap)} sets saved to data/sitemap_cache.json')
        else:
            print('ERROR: sitemap empty!')

asyncio.run(build())
"

echo "=== DONE ==="
