#!/usr/bin/env python3
"""
Parse mediaexpert category page HTML (from cf_solver) — find product IDs & data.
Then test GraphQL polling with those IDs.
"""
import asyncio
import json
import os
import sys
import re
import time

os.environ.setdefault("DISPLAY", ":99")
sys.path.insert(0, "/opt/pokemon-monitor-v2")


async def main():
    from cf_solver import solve, _ensure_browser, _contexts, close
    
    # Step 1: Get category page
    print("=== CF Solve: Pokemon karty kolekcjonerskie ===")
    url = "https://www.mediaexpert.pl/karty-kolekcjonerskie/pokemon-karty-kolekcjonerskie"
    html = await solve(url, timeout=45)
    
    if not html:
        print("FAILED!")
        return
    
    print(f"HTML: {len(html)} bytes")
    
    # Save for analysis
    with open("/tmp/me_category.html", "w") as f:
        f.write(html)
    
    # Find all patterns that look like product/offer IDs
    # Pattern 1: offer-box with class containing ID
    offer_classes = re.findall(r'class="[^"]*offer-(\d+)[^"]*"', html)
    print(f"\noffer-NNNN classes: {len(offer_classes)} → {offer_classes[:10]}")
    
    # Pattern 2: data-product-id or similar
    data_pids = re.findall(r'data-product-id="(\d+)"', html)
    print(f"data-product-id: {len(data_pids)} → {data_pids[:10]}")
    
    # Pattern 3: product ID in href
    product_hrefs = re.findall(r'href="(/[^"]*pokemon[^"]*)"', html, re.IGNORECASE)
    print(f"Pokemon hrefs: {len(product_hrefs)} → {product_hrefs[:5]}")
    
    # Pattern 4: JSON in script tags
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    for i, s in enumerate(scripts):
        if 'product' in s.lower() and len(s) < 50000:
            if 'price' in s.lower() or 'offer' in s.lower() or 'stock' in s.lower():
                print(f"\nScript [{i}] ({len(s)} chars) has product+price/offer/stock:")
                print(f"  {s[:500]}")
    
    # Pattern 5: dataLayer / GTM
    dl_match = re.findall(r'dataLayer\.push\((.*?)\);', html, re.DOTALL)
    for i, dl in enumerate(dl_match[:5]):
        if 'product' in dl.lower() or 'item' in dl.lower():
            print(f"\ndataLayer push [{i}]: {dl[:500]}")
    
    # Pattern 6: meta product tags
    metas = re.findall(r'<meta[^>]*property="product[^"]*"[^>]*>', html)
    print(f"\nProduct meta tags: {len(metas)}")
    for m in metas[:10]:
        print(f"  {m}")
    
    # Pattern 7: aria-label on offer boxes
    offer_labels = re.findall(r'aria-label="([^"]*)"[^>]*class="[^"]*offer', html)
    print(f"\nOffer aria-labels: {len(offer_labels)}")
    for ol in offer_labels[:5]:
        print(f"  {ol[:80]}")
    
    # Pattern 8: search for "unavailable" / "niedostępny" / "wycofany"
    unavail_count = html.lower().count('niedost')
    wycofany_count = html.lower().count('wycofan')
    avail_count = html.lower().count('dodaj do koszyka')
    print(f"\nAvailability signals: niedost={unavail_count}, wycofany={wycofany_count}, dodaj_do_koszyka={avail_count}")
    
    # Pattern 9: prodsklimat IDs (from earlier sniff)
    prodsklimat = re.findall(r'prodsklimat\s*=\s*\[([\d,\s]+)\]', html)
    if prodsklimat:
        ids = [x.strip() for x in prodsklimat[0].split(",") if x.strip()]
        print(f"\nprodsklimat IDs: {len(ids)} → {ids[:10]}")
    
    # Step 2: If we found offer IDs, try GraphQL
    test_ids = offer_classes[:5] or data_pids[:5]
    if test_ids:
        print(f"\n=== GraphQL test with IDs: {test_ids} ===")
        await _ensure_browser()
        if _contexts:
            ctx = _contexts[0]
            page = await ctx.new_page()
            try:
                ids_str = ",".join(f'"{i}"' for i in test_ids)
                query = f'query Q{{byId(identifierName:"productId",identifierValues:[{ids_str}]){{id product_id price_gross promo_price_gross _embedded{{ozg{{status}}pickupDate{{pos_delivery_display_label customer_delivery_display_label}}}}}}}}'
                ts = int(time.time())
                gql_url = f"https://www.mediaexpert.pl/api/graphql/product-offer/query/{ts}?query={query}"
                
                resp = await page.request.get(gql_url)
                body = await resp.text()
                print(f"  Status: {resp.status} | Size: {len(body)}")
                print(f"  Body: {body[:2000]}")
            finally:
                await page.close()
    
    await close()

asyncio.run(main())
