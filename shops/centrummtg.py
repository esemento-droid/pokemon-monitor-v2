"""
Scraper: centrum-mtg.com.pl (Sellingo + nodea PoW)
Kategoria: /pokemon
Platform: Sellingo (sellasist)
Anti-bot: nodea SHA-256 PoW (diff=17)
"""

import asyncio
import hashlib
import re

import aiohttp
from bs4 import BeautifulSoup

SHOP = "centrummtg"
BASE = "https://www.centrum-mtg.com.pl"
CATEGORY_URL = f"{BASE}/pokemon"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

EXCLUDE = [
    "ultra pro", "koszulk", "sleeve", "playmat", "album", "portfolio", "binder", "toploader",
    "holder", "deck box", "battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "wcs ", "battle academy", "japoński", "japońsk",
    "japanese", "(jp)", "koreański", "koreańsk", "korean", "chiński", "chińsk", "chinese",
    "(chi)", "s-chinese", "ultra-pro", "segregator", "alcove", "lorcana", "one piece",
    "yu-gi-oh", "digimon", "naruto", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"
]


def _solve_pow(token: str, diff: int) -> int:
    """Brute-force SHA-256 nonce where hash has >= diff leading zero bits."""
    nonce = 0
    while True:
        h = hashlib.sha256(f"{token}|{nonce}".encode()).digest()
        bits = 0
        for byte in h:
            if byte == 0:
                bits += 8
                continue
            for bit in range(7, -1, -1):
                if not (byte & (1 << bit)):
                    bits += 1
                else:
                    break
            break
        if bits >= diff:
            return nonce
        nonce += 1


async def _get_session_cookie(session: aiohttp.ClientSession) -> None:
    """Solve nodea PoW challenge and obtain session cookie."""
    async with session.get(BASE, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        text = await resp.text()

    m = re.search(r'token="([^"]+)",\s*diff=(\d+)', text)
    if not m:
        return

    token = m.group(1)
    diff = int(m.group(2))

    nonce = await asyncio.to_thread(_solve_pow, token, diff)

    data = {"token": token, "nonce": str(nonce), "fp": "{}"}
    async with session.post(
        f"{BASE}/__nodea/verify-js", data=data, timeout=aiohttp.ClientTimeout(total=10)
    ) as resp:
        result = await resp.json()
        if not result.get("ok"):
            raise RuntimeError(f"nodea verify failed: {result}")


def _parse_price(text: str) -> str:
    """Parse price like '1 000,00PLN' -> '1000.00 zl'"""
    text = text.strip()
    text = re.sub(r'[A-Za-z]+$', '', text).strip()
    text = re.sub(r'[\s\xa0]', '', text)
    text = text.replace(',', '.')
    if text:
        return f"{text} zl"
    return ""


def _is_excluded(name: str) -> bool:
    name_lower = name.lower()
    return any(ex in name_lower for ex in EXCLUDE)


async def get_products() -> list[dict]:
    products = []

    async with aiohttp.ClientSession(
        headers={"User-Agent": UA},
        cookie_jar=aiohttp.CookieJar()
    ) as session:
        await _get_session_cookie(session)

        async with session.get(
            CATEGORY_URL, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            text = await resp.text()

        # Detect pagination: /pokemon-1, /pokemon-2, etc.
        page_nums = re.findall(r'href="[^"]*/pokemon-(\d+)"', text)
        pages_to_fetch = []
        if page_nums:
            max_page = max(int(p) for p in page_nums)
            for i in range(1, max_page + 1):
                pages_to_fetch.append(f"{CATEGORY_URL}-{i}")

        all_html = [text]

        for page_url in pages_to_fetch:
            async with session.get(
                page_url, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                all_html.append(await resp.text())

        for html in all_html:
            soup = BeautifulSoup(html, "lxml")
            boxes = soup.select(".c-product-box[data-id]")

            for box in boxes:
                pid = box.get("data-id", "")
                if not pid:
                    continue

                img = box.select_one("img.c-product-box__image")
                name = img.get("alt", "").strip() if img else ""

                if not name or _is_excluded(name):
                    continue

                image = img.get("data-src", "") if img else ""

                a_tag = box.select_one("a.js-product-scope-url")
                url = a_tag["href"] if a_tag and a_tag.get("href") else ""

                price_el = box.select_one("[class*=price]")
                price = _parse_price(price_el.get_text(strip=True)) if price_el else ""

                tags = [t.get_text(strip=True).lower() for t in box.select(".c-product-tag")]
                available = "zamówienie" not in " ".join(tags)

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


if __name__ == "__main__":
    import time
    start = time.time()
    prods = asyncio.run(get_products())
    elapsed = time.time() - start
    avail = [p for p in prods if p["available"]]
    print(f"Total: {len(prods)}, Available: {len(avail)}, Time: {elapsed:.1f}s")
    for p in prods:
        status = "V" if p["available"] else "X"
        print(f"  {status} {p['name'][:60]} | {p['price']}")
