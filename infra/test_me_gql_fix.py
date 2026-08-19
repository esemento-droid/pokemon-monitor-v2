#!/usr/bin/env python3
"""
Debug GraphQL 404 — test exact URL format from browser sniff.
Original captured URL:
/api/graphql/product-offer/query/1781161605?query=query+QuerySimpleProductOfferByProduct{byId(identifierName:"productId",identifierValues:["11689811"]...
"""
import asyncio
import json
import os
import sys
import time
import urllib.parse

os.environ.setdefault("DISPLAY", ":99")
sys.path.insert(0, "/opt/pokemon-monitor-v2")


async def main():
    from patchright.async_api import async_playwright
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox", "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--proxy-server=http://127.0.0.1:8888",
            ]
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()
        
        # First: navigate to mediaexpert to get CF cookies
        print("=== Step 1: Navigate to ME search ===")
        await page.goto(
            "https://www.mediaexpert.pl/search?query[menu_item]=&query[querystring]=pokemon+tcg",
            wait_until="domcontentloaded", timeout=45000
        )
        await asyncio.sleep(5)
        
        # Get product IDs from page
        print("=== Step 2: Extract product IDs ===")
        ids_raw = await page.evaluate("""
            () => {
                const boxes = document.querySelectorAll('.offer-box');
                const ids = [];
                for (const box of boxes) {
                    const cls = box.className || '';
                    const m = cls.match(/offer-(\\d+)/);
                    if (m) ids.push(m[1]);
                }
                return ids;
            }
        """)
        print(f"  Found IDs: {ids_raw}")
        
        if not ids_raw:
            print("  No IDs found! Trying meta tags...")
            ids_raw = await page.evaluate("""
                () => {
                    const meta = document.querySelector('meta[property="product:skusPage"]');
                    if (meta) return meta.content.split(',').filter(x => x.trim());
                    return [];
                }
            """)
            print(f"  Meta IDs: {ids_raw}")
        
        if not ids_raw:
            print("FAILED — no product IDs")
            await browser.close()
            return
        
        # Step 3: Test different GraphQL URL formats
        print(f"\n=== Step 3: Test GraphQL formats with IDs {ids_raw[:3]} ===")
        
        test_ids = ids_raw[:3]
        ts = int(time.time())
        
        # Format 1: Exact copy from sniff (query+Name{...})
        ids_str1 = ",".join(f'"{i}"' for i in test_ids)
        q1 = f'query QuerySimpleProductOfferByProduct{{byId(identifierName:"productId",identifierValues:[{ids_str1}]){{id product_id price_gross promo_price_gross _embedded{{ozg{{status}}pickupDate{{pos_delivery_display_label customer_delivery_display_label}}}}}}}}'
        url1 = f"https://www.mediaexpert.pl/api/graphql/product-offer/query/{ts}?query={urllib.parse.quote(q1)}"
        
        # Format 2: URL encoded with + for spaces
        q2 = q1.replace(" ", "+")
        url2 = f"https://www.mediaexpert.pl/api/graphql/product-offer/query/{ts}?query={q2}"
        
        # Format 3: Without query name
        q3 = f'{{byId(identifierName:"productId",identifierValues:[{ids_str1}]){{id product_id price_gross promo_price_gross _embedded{{ozg{{status}}}}}}}}'
        url3 = f"https://www.mediaexpert.pl/api/graphql/product-offer/query/{ts}?query={urllib.parse.quote(q3)}"
        
        formats = [
            ("Sniff-exact (url-encoded)", url1),
            ("Plus-spaces", url2),
            ("No query name", url3),
        ]
        
        for name, url in formats:
            print(f"\n  [{name}]")
            print(f"    URL: {url[:120]}...")
            
            # Test via page.evaluate(fetch)
            fetch_js = """
                async (url) => {
                    try {
                        const resp = await fetch(url, {
                            method: "GET",
                            headers: {"Accept": "application/json"},
                            credentials: "same-origin"
                        });
                        const text = await resp.text();
                        return JSON.stringify({status: resp.status, body: text.substring(0, 1000)});
                    } catch(e) {
                        return JSON.stringify({error: e.message});
                    }
                }
            """
            result = await page.evaluate(fetch_js, url)
            data = json.loads(result)
            print(f"    Status: {data.get('status', data.get('error', '?'))}")
            body = data.get('body', '')
            if body and len(body) > 10:
                print(f"    Body: {body[:500]}")
        
        # Format 4: page.request.get (uses browser context directly)
        print(f"\n  [page.request.get]")
        try:
            resp = await page.request.get(url1, timeout=10000)
            body = await resp.text()
            print(f"    Status: {resp.status}")
            print(f"    Body: {body[:500]}")
        except Exception as e:
            print(f"    Error: {e}")
        
        await browser.close()

asyncio.run(main())
