#!/usr/bin/env python3
"""
Test: Use cf_solver to get CF cookies, then poll GraphQL product-offer API.
This is the path to instant mediaexpert monitoring (HTTP poll, no browser per scan).
"""
import asyncio
import json
import os
import sys
import re
import time

os.environ.setdefault("DISPLAY", ":99")
sys.path.insert(0, "/opt/pokemon-monitor-v2")

import aiohttp


async def main():
    # Step 1: Use cf_solver to get page HTML + cookies (CF bypass)
    print("=== Step 1: CF Solve category page ===")
    from cf_solver import solve
    
    category_url = "https://www.mediaexpert.pl/karty-kolekcjonerskie/pokemon-karty-kolekcjonerskie"
    html = await solve(category_url, timeout=45)
    
    if not html:
        print("CF solve FAILED!")
        return
    
    print(f"  Got HTML: {len(html)} bytes")
    
    # Extract SKU IDs from meta tags
    skus_match = re.search(r'product:skusPage["\s]+content="([^"]+)"', html)
    skus_after = re.search(r'product:skusafter5["\s]+content="([^"]+)"', html)
    
    all_skus = []
    if skus_match:
        all_skus.extend(skus_match.group(1).split(","))
    if skus_after:
        all_skus.extend(skus_after.group(1).split(","))
    all_skus = [s.strip() for s in all_skus if s.strip()]
    
    print(f"  Found {len(all_skus)} SKU IDs: {all_skus[:10]}...")
    
    # Extract product data from offer-box elements (same as current scraper)
    # But also look for __NEXT_DATA__ or product JSON
    products_json = re.findall(r'"product_id":(\d+)', html)
    print(f"  Product IDs in HTML: {products_json[:10]}")
    
    # Look for productId in data attributes
    offer_ids = re.findall(r'offer-(\d+)', html)
    print(f"  Offer IDs: {offer_ids[:10]}")
    
    # Step 2: Try GraphQL with CF cookies (via cf_solver browser context)
    print("\n=== Step 2: GraphQL via cf_solver context ===")
    
    # cf_solver uses persistent contexts — let's extract cookies from it
    from cf_solver import _browser, _contexts, _ensure_browser
    await _ensure_browser()
    
    if _contexts:
        ctx = _contexts[0]
        cookies = await ctx.cookies()
        print(f"  Context has {len(cookies)} cookies")
        cf_cookies = {c['name']: c['value'] for c in cookies if 'mediaexpert' in c.get('domain', '')}
        print(f"  ME cookies: {list(cf_cookies.keys())}")
        
        # Now try GraphQL with a page in this context
        page = await ctx.new_page()
        try:
            # Use SKUs to query offers
            if all_skus:
                test_skus = all_skus[:5]
                ids_str = ",".join(f'"{s}"' for s in test_skus)
                query = f'query QuerySimpleProductOfferByProduct{{byId(identifierName:"productId",identifierValues:[{ids_str}]){{id product_id price_gross discount promo_price_gross _embedded{{promoPrice{{price_gross}}pickupDate{{pos_delivery_display_label customer_delivery_display_label}}ozg{{status}}}}}}}}'
                
                ts = int(time.time())
                url = f"https://www.mediaexpert.pl/api/graphql/product-offer/query/{ts}?query={query}"
                
                print(f"\n  Fetching GraphQL: {url[:100]}...")
                resp = await page.request.get(url)
                status = resp.status
                body = await resp.text()
                print(f"  Status: {status}")
                print(f"  Response ({len(body)} bytes): {body[:2000]}")
                
                if status == 200:
                    data = json.loads(body)
                    offers = data.get("data", {}).get("byId", [])
                    print(f"\n  === {len(offers)} OFFERS ===")
                    for o in offers:
                        pid = o.get("product_id")
                        price = o.get("price_gross")
                        promo = o.get("promo_price_gross")
                        ozg = o.get("_embedded", {}).get("ozg", {}).get("status")
                        pickup = o.get("_embedded", {}).get("pickupDate", {})
                        print(f"    PID={pid} | price={price} | promo={promo} | ozg={ozg} | pickup={pickup}")
        finally:
            await page.close()
    
    # Step 3: Also try direct aiohttp with cookie jar
    print("\n=== Step 3: Direct aiohttp with CF cookies ===")
    if cf_cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cf_cookies.items())
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Cookie": cookie_header,
            "Accept": "application/json",
            "Referer": "https://www.mediaexpert.pl/karty-kolekcjonerskie/pokemon-karty-kolekcjonerskie",
        }
        
        if all_skus:
            test_skus = all_skus[:3]
            ids_str = ",".join(f'"{s}"' for s in test_skus)
            query = f'query Q{{byId(identifierName:"productId",identifierValues:[{ids_str}]){{id product_id price_gross promo_price_gross _embedded{{ozg{{status}}}}}}}}'
            ts = int(time.time())
            url = f"https://www.mediaexpert.pl/api/graphql/product-offer/query/{ts}?query={query}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    print(f"  aiohttp status: {resp.status}")
                    body = await resp.text()
                    print(f"  Response: {body[:1000]}")
    
    from cf_solver import close
    await close()


asyncio.run(main())
