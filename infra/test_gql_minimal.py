#!/usr/bin/env python3
"""Minimal GraphQL test — try every possible URL variant."""
import asyncio, os, sys, json
os.environ.setdefault("DISPLAY", ":99")
sys.path.insert(0, "/opt/pokemon-monitor-v2")

async def main():
    from shops.mediaexpert import scan_with_page, _product_catalog, EXTRACT_JS
    from patchright.async_api import async_playwright
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-gpu",
                  "--disable-blink-features=AutomationControlled",
                  "--proxy-server=http://127.0.0.1:8888"]
        )
        ctx = await browser.new_context()
        page = await ctx.new_page()
        
        # Do full scan first (to get on ME page with cookies)
        print("=== Full scan (goto) ===")
        products = await scan_with_page(page)
        print(f"Got {len(products)} products")
        if not products:
            await browser.close()
            return
        
        pids = [p["id"].replace("mediaexpert_", "") for p in products]
        print(f"PIDs: {pids}")
        
        # Now page is ON mediaexpert.pl — test GraphQL
        print(f"\nCurrent page URL: {page.url}")
        
        # Test ALL variants
        test_js = """
            async () => {
                const pids = %s;
                const results = [];
                const idsStr = pids.map(id => '"' + id + '"').join(',');
                const ts = Math.floor(Date.now() / 1000);
                
                // Query variants
                const q1 = 'query QuerySimpleProductOfferByProduct{byId(identifierName:"productId",identifierValues:[' + idsStr + ']){id product_id price_gross}}';
                const q2 = '{byId(identifierName:"productId",identifierValues:[' + idsStr + ']){id product_id price_gross}}';
                
                // URL variants
                const tests = [
                    ['/api/graphql/product-offer/query/' + ts + '?query=' + encodeURIComponent(q1), 'relative+encode+fullname'],
                    ['https://www.mediaexpert.pl/api/graphql/product-offer/query/' + ts + '?query=' + encodeURIComponent(q1), 'absolute+encode+fullname'],
                    ['/api/graphql/product-offer/query/' + ts + '?query=' + encodeURIComponent(q2), 'relative+encode+noname'],
                    ['/api/graphql/product-offer/query?query=' + encodeURIComponent(q1), 'no-timestamp'],
                    ['/api/product-offers/comparisons/groups-ids', 'known-working-endpoint'],
                ];
                
                for (const [url, label] of tests) {
                    try {
                        const resp = await fetch(url, {credentials: 'same-origin', headers: {'Accept': 'application/json'}});
                        const text = await resp.text();
                        results.push({label, status: resp.status, size: text.length, body: text.substring(0, 300)});
                    } catch(e) {
                        results.push({label, status: -1, body: e.message});
                    }
                }
                return JSON.stringify(results, null, 2);
            }
        """ % json.dumps(pids)
        
        print("\n=== GraphQL Tests ===")
        result = await page.evaluate(test_js)
        data = json.loads(result)
        for r in data:
            print(f"\n  [{r.get('label')}] status={r.get('status')} size={r.get('size', '?')}")
            body = r.get('body', '')
            if body:
                print(f"    {body[:250]}")
        
        await browser.close()

asyncio.run(main())
