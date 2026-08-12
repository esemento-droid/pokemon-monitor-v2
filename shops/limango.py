"""
Scraper: limango.pl — Klocki LEGO (outlet flash-sale)
URLs: /shop/lego + /s/klocki+lego
Platform: limango (Otto Group) — SSR + possible JS hydration
Strategy: aiohttp + regex parsing (fast), fallback: patchright if CF blocks

Filtr: TYLKO zestawy klocków LEGO (nie ubrania/plecaki/akcesoria marki LEGO)
Rozpoznawanie klocków: "LEGO®" w nazwie + wiek ("od X lat"/"vanaf X jaar"/numer zestawu)
"""

import asyncio
import re
import ssl

import aiohttp
from bs4 import BeautifulSoup

SHOP = "limango"
BASE = "https://www.limango.pl"

# Multiple search strategies — klocki LEGO mogą być pod różnymi URL
URLS = [
    f"{BASE}/shop/lego",
    f"{BASE}/s/klocki+lego",
    f"{BASE}/s/lego+klocki",
]

# Pagination — limango uses ?page=N or ?offset=N
MAX_PAGES = 5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
}

# Keywords indicating actual LEGO brick sets (not clothing/accessories)
LEGO_SET_INDICATORS = [
    "lego®",
    "lego ®",
    "od ", " lat",           # "od 6 lat" = age indicator (PL)
    "vanaf ", " jaar",       # Dutch age indicator (limango shared platform)
    "klocki",
    "zestaw",
    "elementy",              # "XXX elementów"
    "minifigur",
]

# If name contains these — it's clothing/accessories, NOT brick sets
CLOTHING_KEYWORDS = [
    "kurtk", "jas ", "jacket", "softshell", "winterjas",
    "shirt", "t-shirt", "longsleeve", "hoodie", "sweat",
    "spodni", "broek", "short", "leggins",
    "czapk", "muts", "szalik", "rkawic", "handschoen", "nekwarmer", "bivakmuts",
    "plecak", "rugzak", "schooltas", "etui", "torb",
    "piżam", "pyjama", "jumpsuit", "body",
    "skarpet", "sock", "boxer", "hipster", "bielizn",
    "buty", "sandal", "sneaker", "kapcie",
    "pościel", "ręcznik", "koc ",
    "bidon", "lunch", "śniadani",
    "fleece", "vest", "bodywarmer",
    "ski-", "snowboard", "regenjas", "regenoutfit",
    "sneeuwpak", "zwemshirt", "zwemshort",
    "functionele",
]

# Additional LEGO set number pattern (5-digit number like 10270, 60415, 42151)
LEGO_SET_NUMBER_RE = re.compile(r'\b\d{4,6}\b')

# LEGO themes that confirm it's a brick set
LEGO_THEMES = [
    "city", "friends", "technic", "creator", "classic", "duplo",
    "ninjago", "star wars", "marvel", "disney", "minecraft",
    "speed champions", "architecture", "icons", "ideas",
    "super mario", "harry potter", "lord of the rings",
    "botanicals", "art", "horizon", "sonic", "animal crossing",
    "indiana jones", "jurassic", "monkie kid", "dreamzzz",
]


def is_lego_set(name: str) -> bool:
    """Determine if product name refers to actual LEGO brick set vs clothing."""
    low = name.lower().strip()

    # Quick reject — if it matches clothing keywords, it's NOT a set
    for kw in CLOTHING_KEYWORDS:
        if kw in low:
            return False

    # Check for LEGO® trademark symbol — strong indicator of official set
    if "lego®" in low or "lego ®" in low:
        return True

    # Check for LEGO theme names
    for theme in LEGO_THEMES:
        if theme in low:
            return True

    # Check for age indicator ("od X lat" in Polish)
    if re.search(r'od\s+\d+\s*lat', low):
        return True

    # Check for piece count ("XXX elementów/elem/klocków")
    if re.search(r'\d+\s*(element|klock|piece|deel)', low):
        return True

    # Check for set number pattern (e.g. "10270", "60415")
    if re.search(r'\b[1-9]\d{3,5}\b', low) and ("lego" in low or "klocki" in low):
        return True

    # "klocki" or "zestaw" in name
    if "klocki" in low or "zestaw" in low:
        return True

    return False


def extract_price(text: str) -> str:
    """Extract price from text like '149,99 zł' or '€ 43,99'."""
    # Polish format: 149,99 zł
    m = re.search(r'(\d+[.,]\d{2})\s*zł', text)
    if m:
        return f"{m.group(1).replace(',', '.')} zl"

    # Alternative: just digits with comma
    m = re.search(r'(\d+[.,]\d{2})\s*(?:PLN|zl)', text, re.IGNORECASE)
    if m:
        return f"{m.group(1).replace(',', '.')} zl"

    # Fallback: first price-like pattern
    m = re.search(r'(\d+[.,]\d{2})', text)
    if m:
        return f"{m.group(1).replace(',', '.')} zl"

    return ""


async def _fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch a single page, handle SSL and errors gracefully."""
    # Create SSL context that doesn't verify (limango has cert issues from some IPs)
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=30),
            ssl=ssl_ctx,
        ) as resp:
            if resp.status != 200:
                return ""
            return await resp.text()
    except Exception:
        # Retry without SSL workaround
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    return ""
                return await resp.text()
        except Exception:
            return ""


def _parse_products_from_html(html: str, seen: set) -> list[dict]:
    """Parse LEGO set products from limango HTML page."""
    products = []
    if not html:
        return products

    soup = BeautifulSoup(html, "lxml")

    # Strategy 1: Look for product cards/tiles (common limango selectors)
    # limango uses various class patterns across versions
    selectors = [
        "[data-testid*='product']",
        ".product-card",
        ".product-tile",
        ".product-item",
        ".offer-card",
        ".ProductCard",
        "article[class*='product']",
        "div[class*='ProductCard']",
        "div[class*='product-card']",
        "a[class*='product']",
        "li[class*='product']",
    ]

    items = []
    for sel in selectors:
        found = soup.select(sel)
        if found:
            items = found
            break

    # Strategy 2: If no product cards found, try link-based extraction
    if not items:
        # Find all links that look like product pages
        # limango product URLs: /p/lego-city-xxxx-123456 or /product/...
        product_links = soup.find_all("a", href=re.compile(r'/(p|product)/'))
        if not product_links:
            # Try /shop/ detail links
            product_links = soup.find_all("a", href=re.compile(r'/shop/[^/]+/[^/]+'))

        for link in product_links:
            href = link.get("href", "")
            if not href:
                continue

            # Get the parent container for context
            parent = link.find_parent(["div", "li", "article", "section"])
            if parent and parent not in items:
                items.append(parent)
            elif link not in items:
                items.append(link)

    # Strategy 3: Regex-based extraction from raw HTML (fastest, most reliable for SSR)
    # Pattern: product name with LEGO® + price
    if not items:
        # Try to find JSON-LD structured data
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            try:
                import json
                data = json.loads(script.string or "")
                if isinstance(data, dict) and data.get("@type") == "ItemList":
                    for item in data.get("itemListElement", []):
                        offer = item if item.get("@type") == "Product" else item.get("item", {})
                        if not offer:
                            continue
                        name = offer.get("name", "")
                        if not is_lego_set(name):
                            continue
                        pid = offer.get("sku") or offer.get("productID") or offer.get("url", "").split("/")[-1]
                        if not pid or pid in seen:
                            continue
                        seen.add(pid)

                        price_obj = offer.get("offers", {})
                        if isinstance(price_obj, list):
                            price_obj = price_obj[0] if price_obj else {}
                        price = str(price_obj.get("price", ""))
                        if price:
                            price = f"{price} zl"

                        url = offer.get("url", "")
                        if url and not url.startswith("http"):
                            url = BASE + url

                        image = offer.get("image", "")
                        if isinstance(image, list):
                            image = image[0] if image else ""

                        available = price_obj.get("availability", "").lower()
                        in_stock = "instock" in available or "in_stock" in available

                        products.append({
                            "id": f"{SHOP}_{pid}",
                            "name": name,
                            "price": price,
                            "shop": SHOP,
                            "url": url,
                            "image": image,
                            "stock": "",
                            "available": in_stock,
                        })
                elif isinstance(data, list):
                    for item in data:
                        if item.get("@type") == "Product":
                            name = item.get("name", "")
                            if not is_lego_set(name):
                                continue
                            pid = item.get("sku") or item.get("productID") or ""
                            if not pid or pid in seen:
                                continue
                            seen.add(pid)
                            # ... same extraction
            except (json.JSONDecodeError, TypeError, KeyError):
                continue

    # Process found items (from Strategy 1 or 2)
    for item in items:
        text = item.get_text(" ", strip=True)
        low = text.lower()

        # Skip if doesn't mention LEGO at all
        if "lego" not in low:
            continue

        # Extract name
        name = ""
        # Try common name selectors
        for name_sel in [
            "[class*='name']", "[class*='title']", "[class*='Name']", "[class*='Title']",
            "h2", "h3", "h4", ".product-name", ".product-title",
        ]:
            name_el = item.select_one(name_sel)
            if name_el:
                name = name_el.get_text(" ", strip=True)
                break
        if not name:
            # Use link text or first meaningful text
            a_tag = item.find("a")
            if a_tag:
                name = a_tag.get("title", "") or a_tag.get_text(" ", strip=True)
            if not name:
                # Use first line of text
                name = text[:120]

        if not name or not is_lego_set(name):
            continue

        # Extract URL
        url = ""
        a_tag = item.find("a", href=True)
        if a_tag:
            url = a_tag.get("href", "")
            if url and not url.startswith("http"):
                url = BASE + url

        # Generate product ID from URL or name
        pid = ""
        if url:
            # Try to get ID from URL path
            url_parts = url.rstrip("/").split("/")
            pid = url_parts[-1] if url_parts else ""
            # If URL has query params, strip them
            pid = pid.split("?")[0]

        if not pid:
            # Hash the name as fallback ID
            pid = str(abs(hash(name)))[:10]

        if pid in seen:
            continue
        seen.add(pid)

        # Extract price
        price = extract_price(text)

        # Extract image
        image = ""
        img_tag = item.find("img")
        if img_tag:
            image = img_tag.get("data-src") or img_tag.get("src") or img_tag.get("srcset", "").split(" ")[0]
            if image and not image.startswith("http"):
                image = BASE + image

        # Determine availability
        # limango = outlet, products listed are generally available
        # "wyprzedane" / "uitverkocht" / "sold out" = not available
        available = True
        if any(x in low for x in ["wyprzedane", "niedostępn", "brak", "uitverkocht", "sold out", "niet beschikbaar"]):
            available = False
        if "dodaj do koszyka" in low or "koszyk" in low or "kup" in low:
            available = True

        products.append({
            "id": f"{SHOP}_{pid}",
            "name": name.strip(),
            "price": price,
            "shop": SHOP,
            "url": url,
            "image": image,
            "stock": "",
            "available": available,
        })

    return products


async def get_products() -> list[dict]:
    """Main scraper entry point — fetches LEGO brick sets from limango.pl."""
    products = []
    seen = set()

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for base_url in URLS:
            # Fetch first page
            html = await _fetch_page(session, base_url)
            if not html:
                continue

            page_products = _parse_products_from_html(html, seen)
            products.extend(page_products)

            # Try pagination if products were found
            if page_products:
                tasks = []
                for page in range(2, MAX_PAGES + 1):
                    # limango pagination patterns
                    sep = "&" if "?" in base_url else "?"
                    page_url = f"{base_url}{sep}page={page}"
                    tasks.append(_fetch_page(session, page_url))

                if tasks:
                    pages_html = await asyncio.gather(*tasks)
                    for page_html in pages_html:
                        if page_html:
                            page_prods = _parse_products_from_html(page_html, seen)
                            products.extend(page_prods)

    # Deduplicate by name (some products appear in multiple search results)
    final = []
    seen_names = set()
    for p in products:
        name_key = p["name"].lower().strip()
        if name_key not in seen_names:
            seen_names.add(name_key)
            final.append(p)

    print(f"[LIMANGO] {len(final)} klocki LEGO (filtered from HTML)")
    return final


if __name__ == "__main__":
    import time
    start = time.time()
    prods = asyncio.run(get_products())
    elapsed = time.time() - start
    avail = [p for p in prods if p["available"]]
    print(f"Total: {len(prods)}, Available: {len(avail)}, Time: {elapsed:.1f}s")
    for p in prods:
        status = "V" if p["available"] else "X"
        print(f"  {status} {p['name'][:65]} | {p['price']}")
