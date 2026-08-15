"""
Scraper: efantasy.gr (Greek TCG shop, custom platform)
Auto-discovers all Pokemon TCG subcategories (excl Chinese/Japanese/Singles)
No anti-bot, parallel fetch with concurrency limit
Prices in EUR
"""

import asyncio
import re

import aiohttp
from bs4 import BeautifulSoup

SHOP = "efantasy"
BASE = "https://www.efantasy.gr"
MAIN_URL = f"{BASE}/en/products/pokemon-tcg"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

EXCLUDE_CATS = ["chinese", "japanese", "cards"]
EXCLUDE_PRODUCTS = [
    "sleeves", "playmat", "album", "portfolio",
    "pro-binder", "toploader", "holder", "protector",
    "japanese", "chinese",
]

MAX_CONCURRENT = 3  # max parallel requests to avoid throttle


def _parse_price(text: str) -> str:
    """Parse Greek price: '24,99€' or '2.800,00€' -> '24.99 EUR' or '2800.00 EUR'"""
    text = text.strip().replace("\u20ac", "").replace("€", "").strip()
    text = re.sub(r'[\s\xa0]', '', text)
    if re.match(r'^\d{1,3}(\.\d{3})+(,\d{2})?$', text):
        text = text.replace('.', '').replace(',', '.')
    elif ',' in text:
        text = text.replace(',', '.')
    if text:
        return f"{text} EUR"
    return ""


def _is_excluded(name: str) -> bool:
    name_lower = name.lower()
    return any(ex in name_lower for ex in EXCLUDE_PRODUCTS)


async def _fetch_with_retry(session, url, sem, retries=3):
    """Fetch URL with semaphore limit and retry on disconnect."""
    for attempt in range(retries):
        async with sem:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    return await resp.text()
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(2 * (attempt + 1))
                else:
                    raise
    return ""


async def _discover_categories(session, sem) -> list[str]:
    """Fetch main page and discover all subcategory URLs."""
    html = await _fetch_with_retry(session, MAIN_URL, sem)
    soup = BeautifulSoup(html, "lxml")
    links = soup.select('a[href*="/pokemon-tcg/"]')

    seen = set()
    cats = []
    for a in links:
        href = a.get('href', '')
        if not href or href in seen:
            continue
        if '/pokemon-tcg/' in href and href.count('/') == 5:
            if not any(ex in href.lower() for ex in EXCLUDE_CATS):
                seen.add(href)
                full_url = BASE + href if not href.startswith('http') else href
                cats.append(full_url)

    return cats


def _parse_page(html: str, seen_ids: set) -> list[dict]:
    """Parse products from a category page HTML."""
    products = []
    soup = BeautifulSoup(html, "lxml")
    boxes = soup.select(".product.product-box")

    for box in boxes:
        cart_btn = box.select_one("button.cartbutton[data-product-id]")
        pid = cart_btn.get("data-product-id", "") if cart_btn else ""
        if not pid or pid in seen_ids:
            continue
        seen_ids.add(pid)

        title_a = box.select_one(".product-title a")
        name = title_a.get_text(strip=True) if title_a else ""
        if not name or _is_excluded(name):
            continue

        url = title_a.get("href", "") if title_a else ""
        if url and not url.startswith("http"):
            url = BASE + url

        img = box.select_one(".product-image img")
        image = img.get("src", "") if img else ""

        price_el = box.select_one(".product-price strong")
        price = _parse_price(price_el.get_text(strip=True)) if price_el else ""

        label = box.get("data-label", "")
        available = True  # preorder = mozna kupic

        products.append({
            "id": f"{SHOP}_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": url,
            "image": image,
            "stock": "",
            "available": available,
        })

    return products


async def get_products() -> list[dict]:
    products = []
    seen_ids = set()
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async with aiohttp.ClientSession(
        headers={"User-Agent": UA}
    ) as session:
        # Step 1: Discover categories
        cat_urls = await _discover_categories(session, sem)

        # Step 2: Fetch all categories with limited concurrency
        tasks = [_fetch_with_retry(session, url, sem) for url in cat_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Step 3: Parse all results
        for html in results:
            if isinstance(html, Exception) or not html:
                continue
            page_products = _parse_page(html, seen_ids)
            products.extend(page_products)

    return products


if __name__ == "__main__":
    import time
    start = time.time()
    prods = asyncio.run(get_products())
    elapsed = time.time() - start
    avail = [p for p in prods if p["available"]]
    print(f"Total: {len(prods)}, Available: {len(avail)}, Time: {elapsed:.1f}s")
    for p in prods:
        status = "V" if p["available"] else "X"
        print(f"  {status} {p['name'][:55]} | {p['price']}")
