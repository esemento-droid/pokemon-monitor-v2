import aiohttp
from bs4 import BeautifulSoup
import re

BASE_URL = "https://www.truecollector.pl/pokmon-tcg-c-1.html"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}


async def get_products():
    products = []
    seen_ids = set()

    import asyncio
    async def _fetch(session, page):
        url = BASE_URL if page == 1 else f"{BASE_URL}/s={page}"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return None
                return await resp.text()
        except Exception:
            return None
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        html1 = await _fetch(session, 1)
        if not html1:
            return []
        soup1 = BeautifulSoup(html1, "lxml")
        pags = set()
        for a in soup1.select("a[href]"):
            m = re.search(r"/s=(\d+)", a.get("href", ""))
            if m:
                pags.add(int(m.group(1)))
        max_page = max(pags) if pags else 1
        all_html = [html1]
        if max_page > 1:
            rest = await asyncio.gather(*[_fetch(session, p) for p in range(2, max_page + 1)])
            all_html.extend(rest)
        for html in all_html:
            if not html:
                continue

            soup = BeautifulSoup(html, "lxml")
            items = soup.select("div.Okno.OknoRwd")

            if not items:
                break

            for item in items:
                # ID from div id="prd-XXX-YYY"
                div_id = item.get("id", "")
                pid_match = re.search(r"prd-\d+-(\d+)", div_id)
                if not pid_match:
                    continue
                pid = pid_match.group(1)
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)

                # Name
                name_el = item.find("meta", itemprop="name")
                name = name_el.get("content", "").strip() if name_el else ""
                if not name:
                    continue
                name_lower = name.lower()
                if "japan" in name_lower or "jap " in name_lower or "japanese" in name_lower:
                    continue

                # URL
                url_el = item.find("link", itemprop="url")
                url_prod = url_el.get("href", "") if url_el else ""

                # Price
                price_el = item.find("meta", itemprop="price")
                price = f"{price_el.get('content', '0')} PLN" if price_el else "brak"

                # Availability - ProduktBezZakupu = unavailable
                classes = " ".join(item.get("class", []))
                available = "BezZakupu" not in classes

                # Image
                img_el = item.find("link", itemprop="image")
                image = img_el.get("href", "") if img_el else ""

                products.append({
                    "id": f"truecollector-{pid}",
                    "name": name,
                    "price": price,
                    "shop": "truecollector",
                    "url": url_prod,
                    "image": image,
                    "stock": "",
                    "available": available,
                })

    return products
