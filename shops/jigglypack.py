import aiohttp
import asyncio
import hashlib
import re
from bs4 import BeautifulSoup

SHOP = "jigglypack"
URL = "https://www.jigglypack.pl/kategoria-produktu/pokemon/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
EXCLUDE_TAGS = {"koszulki", "ultra-pro"}

def solve_pow(token, diff):
    """Solve nodea PoW challenge - find nonce where SHA256(token|nonce) has diff leading zero bits."""
    nonce = 0
    while True:
        h = hashlib.sha256(f"{token}|{nonce}".encode()).digest()
        bits = 0
        for byte in h:
            if byte == 0:
                bits += 8
            else:
                for b in range(7, -1, -1):
                    if (byte & (1 << b)) == 0:
                        bits += 1
                    else:
                        break
                break
        if bits >= diff:
            return nonce
        nonce += 1

async def get_session_with_pow(session, url):
    """Fetch URL, solve PoW if needed, return HTML."""
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        html = await resp.text()

    if "Weryfikacja" not in html or "nodea" not in html:
        return html

    token_m = re.search(r'token="([^"]+)"', html)
    diff_m = re.search(r"diff=(\d+)", html)
    if not token_m or not diff_m:
        return ""

    token = token_m.group(1)
    diff = int(diff_m.group(1))

    nonce = await asyncio.get_event_loop().run_in_executor(None, solve_pow, token, diff)

    data = {"token": token, "nonce": str(nonce), "fp": '{"wd":0,"lang":2,"hc":4,"ch":1,"gl":"none"}'}
    base = url.split("/kategoria")[0] if "/kategoria" in url else "https://www.jigglypack.pl"
    async with session.post(f"{base}/__nodea/verify-js", data=data) as resp:
        j = await resp.json()
        if not j.get("ok"):
            return ""

    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        return await resp.text()

def parse_page(html):
    products = []
    soup = BeautifulSoup(html, "lxml")
    for item in soup.select("li.product.type-product"):
        classes = " ".join(item.get("class", []))
        if any(f"product_tag-{tag}" in classes for tag in EXCLUDE_TAGS):
            continue

        pid_el = item.select_one("[data-product_id]")
        if not pid_el:
            continue
        pid = pid_el.get("data_product_id", "") or pid_el.get("data-product_id", "")
        if not pid:
            continue

        name_el = item.select_one("h2.woocommerce-loop-product__title")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            continue

        link_el = item.select_one("a.woocommerce-loop-product__link")
        url_prod = link_el["href"] if link_el and link_el.get("href") else ""

        price_el = item.select_one("span.price .woocommerce-Price-amount bdi")
        if price_el:
            price = price_el.get_text(strip=True).replace("\xa0", " ").replace("zl", "").replace("z\u0142", "").strip() + " zl"
        else:
            price = "brak"

        img_el = item.select_one("img.wp-post-image")
        image = img_el.get("src", "") if img_el else ""

        stock_el = item.select_one(".ct-woo-card-stock .stock")
        if stock_el:
            available = "in-stock" in stock_el.get("class", [])
        else:
            available = "instock" in classes

        products.append({
            "id": f"jigglypack_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": url_prod,
            "image": image,
            "stock": None,
            "available": available,
        })
    return products

async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        html = await get_session_with_pow(session, URL)
        if not html:
            return []

        batch = parse_page(html)
        for p in batch:
            if p["id"] not in seen:
                seen.add(p["id"])
                products.append(p)

        # Check for more pages
        soup = BeautifulSoup(html, "lxml")
        pages = {1}
        for a in soup.select("a.page-numbers"):
            txt = a.get_text(strip=True)
            if txt.isdigit():
                pages.add(int(txt))

        max_page = max(pages)
        for page in range(2, max_page + 1):
            page_url = f"{URL}page/{page}/"
            try:
                async with session.get(page_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        break
                    page_html = await resp.text()
            except:
                break
            batch = parse_page(page_html)
            if not batch:
                break
            for p in batch:
                if p["id"] not in seen:
                    seen.add(p["id"])
                    products.append(p)

    print(f"[JIGGLYPACK] {len(products)} produktow")
    return products
