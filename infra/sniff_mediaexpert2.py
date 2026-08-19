#!/usr/bin/env python3
"""
Sniff mediaexpert.pl API v2 — dig deeper into prod-api.mediaexpert.pl
and spark-state to find product/offer endpoints.
"""
import asyncio
import json
import os
import sys
import re

os.environ.setdefault("DISPLAY", ":99")

async def main():
    from patchright.async_api import async_playwright

    api_calls = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--proxy-server=http://127.0.0.1:8888",
            ]
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()

        # Intercept ALL network — specifically look for product/offer data
        async def on_response(response):
            url = response.url
            # Only interested in potential product/search/offer APIs
            if any(x in url.lower() for x in ["offer", "product", "search", "catalog", "listing", "pokemon", "spark-state"]):
                try:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct or "javascript" in ct:
                        body = await response.text()
                        api_calls.append({
                            "url": url[:200],
                            "status": response.status,
                            "size": len(body),
                            "method": response.request.method,
                            "preview": body[:1000],
                        })
                except:
                    pass

        page.on("response", on_response)

        # Visit a SEARCH page for pokemon
        print("=== Step 1: Search page (pokemon tcg) ===")
        await page.goto(
            "https://www.mediaexpert.pl/search?query[menu_item]=&query[querystring]=pokemon+tcg",
            wait_until="networkidle",
            timeout=60000
        )
        await asyncio.sleep(5)

        # Try to extract spark-state URL from page
        print("\n=== Step 2: Extract spark-state config ===")
        spark_config = await page.evaluate("""
            () => {
                // Look for API config in window/global state
                const results = {};
                
                // Check common patterns
                if (window.__NEXT_DATA__) results.__NEXT_DATA__ = JSON.stringify(window.__NEXT_DATA__).substring(0, 2000);
                if (window.__NUXT__) results.__NUXT__ = JSON.stringify(window.__NUXT__).substring(0, 2000);
                if (window.__APP_STATE__) results.__APP_STATE__ = JSON.stringify(window.__APP_STATE__).substring(0, 2000);
                
                // Look for store/state in scripts
                const scripts = document.querySelectorAll('script');
                for (const s of scripts) {
                    const text = s.textContent || '';
                    if (text.includes('prod-api') || text.includes('offers') || text.includes('products')) {
                        if (text.length < 5000) {
                            results['script_with_api'] = text.substring(0, 2000);
                        }
                    }
                }
                
                // Check for product data in dataLayer
                if (window.dataLayer) {
                    const items = window.dataLayer.filter(x => x.ecommerce || x.items || x.products);
                    if (items.length) results.dataLayer = JSON.stringify(items).substring(0, 3000);
                }
                
                // Check meta tags
                const metas = document.querySelectorAll('meta[property*="product"]');
                if (metas.length) {
                    results.metas = Array.from(metas).map(m => m.outerHTML).join('\\n');
                }
                
                return results;
            }
        """)
        print(f"  Spark config keys: {list(spark_config.keys()) if spark_config else 'NONE'}")
        for k, v in (spark_config or {}).items():
            print(f"\n  [{k}]: {str(v)[:500]}")

        # Now try prod-api directly with common patterns
        print("\n=== Step 3: Probe prod-api.mediaexpert.pl endpoints ===")
        probes = [
            "https://prod-api.mediaexpert.pl/api/offers?limit=5&query=pokemon",
            "https://prod-api.mediaexpert.pl/api/v1/offers?limit=5&query=pokemon",
            "https://prod-api.mediaexpert.pl/api/products?limit=5&query=pokemon",
            "https://prod-api.mediaexpert.pl/api/v1/products?limit=5&query=pokemon",
            "https://prod-api.mediaexpert.pl/api/catalog/products?query=pokemon",
            "https://prod-api.mediaexpert.pl/api/search?q=pokemon+tcg",
            "https://prod-api.mediaexpert.pl/api/v2/offers?query=pokemon",
            "https://prod-api.mediaexpert.pl/api/offers/search?query=pokemon+tcg",
            "https://prod-api.mediaexpert.pl/api/mp/offers?query=pokemon",
            "https://prod-api.mediaexpert.pl/api/mp/products?query=pokemon",
        ]
        
        for url in probes:
            try:
                resp = await page.request.get(url, timeout=10000, headers={
                    "Accept": "application/json",
                    "Origin": "https://www.mediaexpert.pl",
                    "Referer": "https://www.mediaexpert.pl/",
                })
                body = await resp.text()
                print(f"\n  [{resp.status}] {url}")
                print(f"    Size: {len(body)} | Preview: {body[:300]}")
            except Exception as e:
                print(f"\n  [ERR] {url}")
                print(f"    {str(e)[:200]}")

        # Check what happens when we scroll/load more on search page
        print("\n=== Step 4: Check XHR on search interaction ===")
        # Click on a product to see if product page loads via API
        product_link = await page.query_selector('a[href*="/karty-kolekcjonerskie/"]')
        if product_link:
            href = await product_link.get_attribute("href")
            print(f"  Navigating to product: {href}")
            await page.goto(f"https://www.mediaexpert.pl{href}" if href.startswith("/") else href,
                          wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)

        await browser.close()

    # Output
    print("\n" + "=" * 80)
    print(f"PRODUCT-RELATED API CALLS: {len(api_calls)}")
    print("=" * 80)
    for i, call in enumerate(api_calls, 1):
        print(f"\n--- [{i}] {call['method']} {call['status']} ({call['size']}b) ---")
        print(f"  {call['url']}")
        print(f"  {call['preview'][:500]}")

asyncio.run(main())
