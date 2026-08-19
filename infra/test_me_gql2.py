#!/usr/bin/env python3
"""
Test GraphQL from within a page that's already on mediaexpert.pl
Simulates what scan_with_page does after full goto.
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
        
        # Navigate + wait for CF
        print("=== Navigating to ME search ===")
        await page.goto(
            "https://www.mediaexpert.pl/search?query[menu_item]=&query[querystring]=pokemon+tcg",
            wait_until="domcontentloaded", timeout=45000
        )
        await asyncio.sleep(3)
        title = await page.title()
        if "moment" in (title or "").lower():
            print("  CF challenge detected, waiting...")
            await asyncio.sleep(8)
        
        # Dismiss cookies
        await page.evaluate("""() => {
            const bb = document.querySelectorAll('button');
            for (const b of bb) {
                const t = (b.textContent || '').toLowerCase();
                if (t.includes('akceptuj') || t.includes('zgadzam')) { b.click(); return; }
            }
        }""")
        await asyncio.sleep(2)
        
        # Get product IDs
        ids = await page.evaluate("""() => {
            const boxes = document.querySelectorAll('.offer-box');
            return Array.from(boxes).map(b => {
                const m = (b.className || '').match(/offer-(\\d+)/);
                return m ? m[1] : null;
            }).filter(x => x);
        }""")
        print(f"  Product IDs: {ids}")
        
        if not ids:
            print("  Still no IDs — page might be CF blocked. Current title:", await page.title())
            print("  URL:", page.url)
            content_check = await page.evaluate("document.body.innerText.substring(0, 200)")
            print(f"  Body: {content_check}")
            await browser.close()
            return
        
        # Now test GraphQL formats
        print(f"\n=== Testing GraphQL with IDs: {ids[:3]} ===")
        test_ids = ids[:3]
        ts = int(time.time())
        
        # Build query exactly like the sniffed one
        ids_json = ",".join(f'"{i}"' for i in test_ids)
        
        # Test via page.evaluate — the page IS on mediaexpert.pl so it's same-origin
        results = await page.evaluate("""
            async (idsJson) => {
                const ts = Date.now();
                const results = [];
                
                // Format 1: Full query name (as seen in sniff)
                const q1 = `query QuerySimpleProductOfferByProduct{byId(identifierName:"productId",identifierValues:[${idsJson}]){id product_id price_gross promo_price_gross _embedded{ozg{status}pickupDate{pos_delivery_display_label customer_delivery_display_label}}}}`;
                
                // Format 2: Short query name
                const q2 = `{byId(identifierName:"productId",identifierValues:[${idsJson}]){id product_id price_gross promo_price_gross _embedded{ozg{status}}}}`;
                
                const urls = [
                    [`/api/graphql/product-offer/query/${ts}?query=${encodeURIComponent(q1)}`, "Full name + encodeURI"],
                    [`/api/graphql/product-offer/query/${ts}?query=${q1}`, "Full name + raw"],
                    [`/api/graphql/product-offer/query/${ts}?query=${encodeURIComponent(q2)}`, "No name + encodeURI"],
                    [`/api/graphql/product-offer/query/${ts}?query=${q2}`, "No name + raw"],
                ];
                
                for (const [url, label] of urls) {
                    try {
                        const resp = await fetch(url, {
                            headers: {"Accept": "application/json"},
                            credentials: "same-origin"
                        });
                        const text = await resp.text();
                        results.push({label, status: resp.status, body: text.substring(0, 500)});
                    } catch(e) {
                        results.push({label, status: -1, body: e.message});
                    }
                }
                return JSON.stringify(results);
            }
        """, ids_json)
        
        data = json.loads(results)
        for r in data:
            print(f"\n  [{r['label']}] Status: {r['status']}")
            print(f"    {r['body'][:400]}")
        
        await browser.close()

asyncio.run(main())
