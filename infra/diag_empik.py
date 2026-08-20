#!/usr/bin/env python3
"""Diagnostyka empik — czas scanu z krótszymi sleepami"""
import asyncio
import time
import sys
sys.path.insert(0, "/opt/pokemon-monitor-v2")

async def main():
    from patchright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled",
                  "--proxy-server=http://127.0.0.1:8888"]
        )
        page = await browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        
        start = time.time()
        from shops.empik import scan_with_page
        products = await scan_with_page(page)
        elapsed = time.time() - start
        
        avail = [p for p in products if p["available"]]
        print(f"\n=== EMPIK: {len(products)} produktow ({len(avail)} available) in {elapsed:.1f}s ===")
        await browser.close()

asyncio.run(main())
