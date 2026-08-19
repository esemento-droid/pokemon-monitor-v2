#!/usr/bin/env python3
"""
Sniff mediaexpert.pl network requests to find internal API endpoints.
Intercepts all XHR/Fetch to find JSON APIs for product data & availability.
Run on VPS: DISPLAY=:99 ./venv/bin/python3 infra/sniff_mediaexpert.py
"""
import asyncio
import json
import os
import sys

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

        # Intercept ALL network requests
        async def on_response(response):
            url = response.url
            ct = response.headers.get("content-type", "")
            # Only care about JSON/API responses
            if "json" in ct or "api" in url.lower() or "graphql" in url.lower() or "gateway" in url.lower():
                try:
                    body = await response.text()
                    size = len(body)
                    preview = body[:500] if size > 0 else ""
                    api_calls.append({
                        "url": url,
                        "status": response.status,
                        "content_type": ct,
                        "size": size,
                        "method": response.request.method,
                        "preview": preview,
                    })
                except:
                    api_calls.append({
                        "url": url,
                        "status": response.status,
                        "content_type": ct,
                        "size": -1,
                        "method": response.request.method,
                        "preview": "(could not read body)",
                    })

        page.on("response", on_response)

        # 1. Visit search page
        print("=== Visiting search page ===")
        await page.goto(
            "https://www.mediaexpert.pl/search?query[menu_item]=&query[querystring]=pokemon+tcg",
            wait_until="networkidle",
            timeout=60000
        )
        await asyncio.sleep(3)

        # 2. Visit a product page (pokemon TCG product)
        print("\n=== Visiting product page ===")
        await page.goto(
            "https://www.mediaexpert.pl/karty-kolekcjonerskie/pokemon-karty-kolekcjonerskie",
            wait_until="networkidle",
            timeout=60000
        )
        await asyncio.sleep(3)

        # 3. Try known API patterns
        print("\n=== Testing common API patterns ===")
        test_urls = [
            "https://www.mediaexpert.pl/api/offers?query=pokemon",
            "https://www.mediaexpert.pl/api/v1/products?q=pokemon",
            "https://www.mediaexpert.pl/gateway/products?q=pokemon",
            "https://www.mediaexpert.pl/prod-api/offers?q=pokemon",
        ]
        for url in test_urls:
            try:
                resp = await page.request.get(url, timeout=10000)
                ct = resp.headers.get("content-type", "")
                body = await resp.text()
                api_calls.append({
                    "url": url,
                    "status": resp.status,
                    "content_type": ct,
                    "size": len(body),
                    "method": "GET (probe)",
                    "preview": body[:500],
                })
            except Exception as e:
                api_calls.append({
                    "url": url,
                    "status": -1,
                    "content_type": "error",
                    "size": 0,
                    "method": "GET (probe)",
                    "preview": str(e)[:200],
                })

        await browser.close()

    # Output results
    print("\n" + "=" * 80)
    print(f"CAPTURED {len(api_calls)} API/JSON RESPONSES")
    print("=" * 80)

    for i, call in enumerate(api_calls, 1):
        print(f"\n--- [{i}] {call['method']} {call['status']} ---")
        print(f"  URL: {call['url'][:150]}")
        print(f"  CT: {call['content_type']}")
        print(f"  Size: {call['size']} bytes")
        if call['preview']:
            print(f"  Preview: {call['preview'][:300]}")

    # Also dump full JSON for analysis
    with open("/tmp/mediaexpert_api_sniff.json", "w") as f:
        json.dump(api_calls, f, indent=2, ensure_ascii=False)
    print(f"\nFull dump: /tmp/mediaexpert_api_sniff.json")

asyncio.run(main())
