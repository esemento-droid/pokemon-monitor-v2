import asyncio
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)
SHOP = "piwniczaki"
BASE_URL = "https://www.sklep-piwniczaki.pl/pokemon-tcg"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
MAX_PAGES = 5

JS_EXTRACT = "els => els.map(el => ({title: (el.querySelector('.c-product-box__title') || {}).textContent || '', price: (el.querySelector('.c-product-box__price-value') || {}).textContent || '', img: (el.querySelector('img') || {}).getAttribute('data-src') || (el.querySelector('img') || {}).getAttribute('data-lazy') || (el.querySelector('img') || {}).src || '', link: (el.querySelector('a[href*=piwniczaki]') || {}).href || '', avail: el.querySelector('.c-avaibility') ? el.querySelector('.c-avaibility').className : '', btn: el.querySelector('[data-product-id]') ? el.querySelector('[data-product-id]').getAttribute('data-product-id') : ''}))"


async def get_products():
    products = []
    seen_ids = set()
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                for pg in range(1, MAX_PAGES + 1):
                    url = BASE_URL if pg == 1 else f"{BASE_URL}/name_asc/{pg}"
                    ctx = await browser.new_context(user_agent=USER_AGENT)
                    page = await ctx.new_page()
                    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    await asyncio.sleep(5)
                    items = await page.eval_on_selector_all(".c-product-box", JS_EXTRACT)
                    await ctx.close()
                    for item in items:
                        pid = item.get("btn", "")
                        if not pid or pid in seen_ids:
                            continue
                        seen_ids.add(pid)
                        name = item.get("title", "").strip()
                        if not name:
                            continue
                        price_raw = item.get("price", "").strip()
                        price = f"{price_raw} PLN" if price_raw else "brak"
                        available = "--none" not in item.get("avail", "")
                        products.append({"id": f"piwniczaki_{pid}", "name": name, "price": price, "shop": SHOP, "url": item.get("link", ""), "image": item.get("img", ""), "stock": 1 if available else 0, "available": available})
            finally:
                await browser.close()
    except Exception as e:
        logger.error(f"[piwniczaki] Error: {e}")
    print(f"[PIWNICZAKI] {len(products)} produktow")
    return products
