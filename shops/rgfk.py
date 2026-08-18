import asyncio
import json
import aiohttp
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

SHOP = "rgfk"
BASE_URL = "https://rgfk.pl/k/51874/pokemon-tcg"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
EXCLUDE = [
    "album", "sleeves", "koszulk", "toploader", "pro-binder", "ultra pro", "playmat", "energy",
    "energia", "gumk", "mata", "battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "wcs ", "battle academy", "japoński", "japońsk",
    "japanese", "(jp)", "koreański", "koreańsk", "korean", "chiński", "chińsk", "chinese",
    "(chi)", "s-chinese", "ultra-pro", "portfolio", "segregator", "deck box", "alcove",
    "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound", "zeszyt", "puzzle", "figurk", "figure set"
]


def parse_page(html):
    """Parse products from HTML."""
    products = []
    soup = BeautifulSoup(html, "lxml")
    items = soup.select("span.tc-product-tile-data")
    for item in items:
        try:
            data = json.loads(item.get("data-product", "{}"))
        except json.JSONDecodeError:
            continue
        pid = data.get("id")
        name = data.get("name", "")
        if not pid or not name or len(name) < 5:
            continue
        if any(ex in name.lower() for ex in EXCLUDE):
            continue
        price_val = data.get("price", 0)
        price = f"{price_val:.2f} zl" if price_val else "brak"
        stock = data.get("stock_quantity", 0)
        available = stock > 0
        card = item.find_parent("div", class_="card-product")
        href = ""
        image = ""
        if card:
            link = card.select_one("a.product-thumbnail")
            if link:
                href = link.get("href", "")
            img = card.select_one("img")
            if img:
                image = img.get("data-src") or img.get("src", "")
        products.append({"id": f"rgfk_{pid}", "name": name, "price": price, "shop": SHOP, "url": href, "image": image, "stock": stock, "available": available})
    return products


async def fetch_with_cookies(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return ""
            return await resp.text()
    except Exception:
        return ""


async def scan_with_page(page):
    """Chrome Pool interface — pass Anubis challenge, get cookies, fetch pages."""
    products = []
    seen_ids = set()

    # Navigate to pass Anubis challenge
    await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
    try:
        await page.wait_for_selector("a.product-thumbnail", timeout=30000)
    except Exception:
        await asyncio.sleep(5)
        content = await page.content()
        if "tc-product-tile-data" not in content:
            print("[RGFK] Anubis challenge not resolved")
            return []

    first_html = await page.content()
    if not first_html or "tc-product-tile-data" not in first_html:
        print("[RGFK] No product data in page")
        return []

    # Get cookies for aiohttp pages 2+
    cookies = await page.context.cookies()
    cookies_dict = {c["name"]: c["value"] for c in cookies}

    # Parse page 1
    page_prods = parse_page(first_html)
    for pr in page_prods:
        if pr["id"] not in seen_ids:
            seen_ids.add(pr["id"])
            products.append(pr)

    # Detect max page
    soup = BeautifulSoup(first_html, "lxml")
    pages = set()
    for a in soup.select("a[href*=page]"):
        href = a.get("href", "")
        if "page=" in href:
            try:
                pg = int(href.split("page=")[1].split("&")[0])
                pages.add(pg)
            except ValueError:
                pass
    max_page = max(pages) if pages else 1

    # aiohttp with cookies for pages 2-max (fast, no Chrome needed)
    if max_page > 1:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
        headers = {"User-Agent": UA, "Cookie": cookie_str}
        async with aiohttp.ClientSession(headers=headers) as session:
            tasks = [fetch_with_cookies(session, f"{BASE_URL}?page={pg}") for pg in range(2, max_page + 1)]
            results = await asyncio.gather(*tasks)
            for html in results:
                if html and "tc-product-tile-data" in html:
                    page_prods = parse_page(html)
                    for pr in page_prods:
                        if pr["id"] not in seen_ids:
                            seen_ids.add(pr["id"])
                            products.append(pr)

    print(f"[RGFK] {len(products)} produktow")
    return products


async def get_products():
    """Legacy interface — fallback/testing."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page(user_agent=UA)
                return await scan_with_page(page)
            finally:
                await browser.close()
    except Exception as e:
        print(f"[RGFK] Browser error: {e}")
        return []
