#!/usr/bin/env python3
"""
Test mediaexpert Synerise Search API + GraphQL product-offer endpoint.
No browser needed — pure HTTP!
"""
import asyncio
import json
import aiohttp

# From spark-state sniff
SYNERISE_INDEX = "bde4319ab3462883803d0d7062ed396f1589349693"
SYNERISE_TOKEN = "AC3815B3-B512-1F8F-F6CB-3754D3D58BF9"
SYNERISE_BASE = f"https://api.synerise.com/search/v2/indices/{SYNERISE_INDEX}/query"

GRAPHQL_BASE = "https://www.mediaexpert.pl/api/graphql/product-offer/query"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.mediaexpert.pl/",
    "Origin": "https://www.mediaexpert.pl",
}


async def test_synerise_search(session):
    """Test Synerise search for Pokemon TCG products."""
    print("=" * 60)
    print("TEST 1: Synerise Search API (pokemon tcg)")
    print("=" * 60)
    
    params = {
        "query": "pokemon tcg",
        "limit": 50,
        "token": SYNERISE_TOKEN,
        "clientUUID": "test-monitor-uuid-001",
    }
    
    async with session.get(SYNERISE_BASE, params=params, headers=HEADERS) as resp:
        print(f"Status: {resp.status}")
        if resp.status == 200:
            data = await resp.json()
            items = data.get("data", [])
            print(f"Results: {len(items)}")
            print(f"\nTop fields in first item: {list(items[0].keys()) if items else 'NONE'}")
            
            # Show first 5 products
            for i, item in enumerate(items[:5], 1):
                attrs = item.get("attributes", {})
                print(f"\n  [{i}] {item.get('title', 'no title')}")
                print(f"      Price: {item.get('price', attrs.get('sale_price_dsc_code', '?'))}")
                print(f"      Brand: {item.get('brand', '?')}")
                print(f"      Category: {item.get('category', '?')}")
                print(f"      URL: {item.get('link', '?')[:80]}")
                print(f"      Image: {attrs.get('image_link_180_180', '?')[:80]}")
                print(f"      In stock: {item.get('availability', attrs.get('availability', '?'))}")
                print(f"      All attrs keys: {list(attrs.keys())}")
            
            # Full JSON of first item for analysis
            if items:
                print(f"\n\n--- FULL FIRST ITEM JSON ---")
                print(json.dumps(items[0], indent=2, ensure_ascii=False)[:3000])
        else:
            print(f"Error: {await resp.text()[:500]}")


async def test_synerise_pokemon_booster(session):
    """Test with 'pokemon booster' query."""
    print("\n\n" + "=" * 60)
    print("TEST 2: Synerise Search (pokemon booster)")
    print("=" * 60)
    
    params = {
        "query": "pokemon booster",
        "limit": 50,
        "token": SYNERISE_TOKEN,
        "clientUUID": "test-monitor-uuid-002",
    }
    
    async with session.get(SYNERISE_BASE, params=params, headers=HEADERS) as resp:
        print(f"Status: {resp.status}")
        if resp.status == 200:
            data = await resp.json()
            items = data.get("data", [])
            print(f"Results: {len(items)}")
            for i, item in enumerate(items[:10], 1):
                attrs = item.get("attributes", {})
                avail = item.get("availability", attrs.get("availability", "?"))
                price = item.get("price", attrs.get("sale_price_dsc_code", "?"))
                print(f"  [{i}] {item.get('title', '?')[:60]} | {price} | stock={avail}")


async def test_graphql_offer(session):
    """Test GraphQL product offer endpoint (price + stock per product ID)."""
    print("\n\n" + "=" * 60)
    print("TEST 3: GraphQL Product Offer (by product ID)")
    print("=" * 60)
    
    # Product IDs from meta tags (pokemon category)
    test_ids = ["2130563", "2130489", "2130490"]
    
    for pid in test_ids:
        query = f'query QuerySimpleProductOfferByProduct{{byId(identifierName:"productId",identifierValues:["{pid}"]){{id product_id price_gross discount promo_price_gross _embedded{{promoPrice{{price_gross}}}}}}}}'
        
        import time
        ts = int(time.time())
        url = f"{GRAPHQL_BASE}/{ts}?query={query}"
        
        async with session.get(url, headers=HEADERS) as resp:
            print(f"\n  Product {pid}: status={resp.status}")
            if resp.status == 200:
                data = await resp.json()
                print(f"    Response: {json.dumps(data, indent=2)[:500]}")
            else:
                body = await resp.text()
                print(f"    Error: {body[:200]}")


async def main():
    async with aiohttp.ClientSession() as session:
        await test_synerise_search(session)
        await test_synerise_pokemon_booster(session)
        await test_graphql_offer(session)


asyncio.run(main())
