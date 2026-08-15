import aiohttp
import asyncio
import hashlib
import re
from bs4 import BeautifulSoup

SHOP = "pikashop"
BASE = "https://pikashop.pl"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
EXCLUDE = ["sleeve", "koszulk", "toploader", "album", "portfolio", "binder", "ultra pro", "playmat", "psa 10", "psa 9", "psa 8", "holder", "karta pokemon"]

def solve_pow(token, diff):
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
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30), proxy="http://127.0.0.1:8888") as resp:
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
    async with session.post(f"{BASE}/__nodea/verify-js", data=data, proxy="http://127.0.0.1:8888") as resp:
        j = await resp.json()
        if not j.get("ok"):
            return ""
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30), proxy="http://127.0.0.1:8888") as resp:
        return await resp.text()

async def get_products():
    products = []
    seen = set()
    search_url = f"{BASE}/?s=Pokemon+tcg&post_type=product"
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        html = await get_session_with_pow(session, search_url)
        if not html:
            print(f"[PIKASHOP] 0 produktow")
            return []
        soup = BeautifulSoup(html, "lxml")
        pages = set()
        for a in soup.select("a[href*=page]"):
            m = re.search(r"page/(\d+)", a.get("href", ""))
            if m:
                pages.add(int(m.group(1)))
        max_page = max(pages) if pages else 1
        all_html = [html]
        for pg in range(2, max_page + 1):
            try:
                async with session.get(f"{BASE}/page/{pg}/?s=Pokemon+tcg&post_type=product", timeout=aiohttp.ClientTimeout(total=45), proxy="http://127.0.0.1:8888") as resp:
                    all_html.append(await resp.text())
            except:
                break
        for pg_html in all_html:
            soup = BeautifulSoup(pg_html, "lxml")
            for prod in soup.select("li.product"):
                cls = " ".join(prod.get("class", []))
                m = re.search(r"post-(\d+)", cls)
                if not m:
                    continue
                pid = m.group(1)
                if pid in seen:
                    continue
                seen.add(pid)
                name_el = prod.select_one("h2, .woocommerce-loop-product__title")
                name = name_el.get_text(strip=True) if name_el else ""
                if not name or len(name) < 5:
                    continue
                if any(ex in name.lower() for ex in EXCLUDE):
                    continue
                link = prod.select_one("a[href]")
                href = link.get("href", "") if link else ""
                price_el = prod.select_one(".price .woocommerce-Price-amount")
                price = "brak"
                if price_el:
                    pm = re.search(r"([\d,.]+)", price_el.get_text())
                    if pm:
                        price = pm.group(1).replace(".", "").replace(",", ".") + " zl"
                available = "instock" in cls
                img = prod.select_one("img")
                image = ""
                if img:
                    for attr in ("data-src", "data-lazy-src", "data-srcset", "srcset", "src"):
                        val = img.get(attr, "")
                        if val and (".jpg" in val or ".png" in val or ".webp" in val):
                            image = val.split(",")[0].split(" ")[0].strip()
                            break
                    if not image:
                        image = img.get("src", "")
                products.append({"id": f"pikashop_{pid}", "name": name, "price": price, "shop": SHOP, "url": href, "image": image, "stock": None, "available": available})
    print(f"[PIKASHOP] {len(products)} produktow")
    return products
