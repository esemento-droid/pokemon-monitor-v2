"""
price_compare.py — Porównanie cen LEGO z promoklocki.pl

Usage:
    from price_compare import compare_price

    result = await compare_price("LEGO City 60412 Wóz strażacki 4x4", 189.99)
    # Returns: {"lowest": 159.90, "diff_pln": -30.09, "diff_pct": -15.8, "source": "promoklocki.pl", "url": "https://promoklocki.pl/60412"}
    # Returns None if set not found or no price available

Primary source: promoklocki.pl (direct HTTP, no CF on product pages)
Fallback: klockoradar.pl (sitemap fuzzy match + JSON-LD)

URL pattern promoklocki.pl: /{set_number} (e.g. /76345)
Data extracted: "Aktualnie najniższa cena" from HTML
"""

import re
import asyncio
import time
from typing import Optional

import aiohttp

# --- Cache ---
_price_cache: dict[str, tuple[float, Optional[float]]] = {}  # key=set_number -> (timestamp, price)
CACHE_TTL = 3600  # 1 hour

# --- Config ---
PROMOKLOCKI_BASE = "https://promoklocki.pl"
KLOCKORADAR_BASE = "https://klockoradar.pl"
KLOCKORADAR_SITEMAP_URLS = [
    f"https://klockoradar.pl/sitemap_{i}.xml" for i in range(1, 9)
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Regex to extract LEGO set number from product name
# Matches: "LEGO City 60412 ..." or "LEGO 76345 ..." or "60412 Wóz..."
SET_NUMBER_RE = re.compile(r'\b(\d{4,6})\b')

# Promoklocki price extraction
PRICE_RE = re.compile(
    r'Aktualnie\s+najni[żz]sza\s+cena\s*'
    r'([\d\s,.]+)\s*z[łl]',
    re.IGNORECASE
)

# Fallback: also try structured data patterns
PRICE_FALLBACK_RE = re.compile(
    r'"lowPrice"\s*:\s*"?([\d.,]+)"?',
    re.IGNORECASE
)

# Klockoradar JSON-LD lowPrice
KLOCKORADAR_PRICE_RE = re.compile(
    r'"lowPrice"\s*:\s*"?([\d.,]+)"?'
)

# Klockoradar sitemap slug matching
_klockoradar_sitemap: dict[str, str] = {}  # set_number -> url
_sitemap_loaded_at: float = 0
SITEMAP_TTL = 21600  # 6 hours


def extract_set_number(name: str) -> Optional[str]:
    """Extract LEGO set number (4-6 digits) from product name."""
    if not name:
        return None
    # Common pattern: "LEGO [Theme] [NUMBER] [Name]"
    # Try to find 5-digit numbers first (most common), then 4 or 6
    numbers = SET_NUMBER_RE.findall(name)
    if not numbers:
        return None
    # Prefer 5-digit numbers (most LEGO sets are 5 digits)
    for n in numbers:
        if len(n) == 5:
            return n
    # Then 6-digit
    for n in numbers:
        if len(n) == 6:
            return n
    # Then 4-digit (older sets)
    for n in numbers:
        if len(n) == 4 and int(n) >= 1000:
            return n
    return numbers[0]


def _parse_price(text: str) -> Optional[float]:
    """Parse Polish price string to float. E.g. '173,90' -> 173.90"""
    if not text:
        return None
    # Remove spaces, replace comma with dot
    cleaned = text.strip().replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


async def _fetch_promoklocki_price(session: aiohttp.ClientSession, set_number: str) -> Optional[float]:
    """Fetch lowest price from promoklocki.pl/{set_number}."""
    url = f"{PROMOKLOCKI_BASE}/{set_number}"
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return None
            html = await resp.text()

        # Primary: "Aktualnie najniższa cena XXX,XX zł"
        match = PRICE_RE.search(html)
        if match:
            price = _parse_price(match.group(1))
            if price and price > 0:
                return price

        # Fallback: JSON-LD lowPrice
        match = PRICE_FALLBACK_RE.search(html)
        if match:
            price = _parse_price(match.group(1))
            if price and price > 0:
                return price

    except (aiohttp.ClientError, asyncio.TimeoutError, Exception) as e:
        print(f"[PRICE_COMPARE] Promoklocki error for {set_number}: {e}")
    return None


async def _load_klockoradar_sitemap(session: aiohttp.ClientSession):
    """Load klockoradar.pl sitemap to map set numbers to URLs."""
    global _klockoradar_sitemap, _sitemap_loaded_at

    if _klockoradar_sitemap and (time.time() - _sitemap_loaded_at) < SITEMAP_TTL:
        return

    new_map = {}
    url_re = re.compile(r'<loc>(https://klockoradar\.pl/sets/[^<]+)</loc>')
    set_num_re = re.compile(r'/sets/(\d+)')

    for sitemap_url in KLOCKORADAR_SITEMAP_URLS:
        try:
            async with session.get(sitemap_url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    continue
                xml = await resp.text()
            for url_match in url_re.finditer(xml):
                page_url = url_match.group(1)
                num_match = set_num_re.search(page_url)
                if num_match:
                    new_map[num_match.group(1)] = page_url
        except Exception:
            continue

    if new_map:
        _klockoradar_sitemap = new_map
        _sitemap_loaded_at = time.time()
        print(f"[PRICE_COMPARE] Klockoradar sitemap: {len(new_map)} sets")


async def _fetch_klockoradar_price(session: aiohttp.ClientSession, set_number: str) -> Optional[float]:
    """Fetch lowest price from klockoradar.pl/sets/{set_number}."""
    await _load_klockoradar_sitemap(session)

    url = _klockoradar_sitemap.get(set_number)
    if not url:
        # Try direct URL pattern
        url = f"{KLOCKORADAR_BASE}/sets/{set_number}"

    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return None
            html = await resp.text()

        match = KLOCKORADAR_PRICE_RE.search(html)
        if match:
            price = _parse_price(match.group(1))
            if price and price > 0:
                return price

    except (aiohttp.ClientError, asyncio.TimeoutError, Exception) as e:
        print(f"[PRICE_COMPARE] Klockoradar error for {set_number}: {e}")
    return None


async def get_lowest_price(set_number: str, session: aiohttp.ClientSession = None) -> Optional[dict]:
    """
    Get lowest market price for a LEGO set.

    Returns dict: {"price": float, "source": str, "url": str} or None
    """
    # Check cache
    if set_number in _price_cache:
        ts, cached_price = _price_cache[set_number]
        if time.time() - ts < CACHE_TTL and cached_price is not None:
            return {
                "price": cached_price,
                "source": "promoklocki.pl",
                "url": f"{PROMOKLOCKI_BASE}/{set_number}"
            }

    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True

    try:
        # Primary: promoklocki.pl
        price = await _fetch_promoklocki_price(session, set_number)
        if price:
            _price_cache[set_number] = (time.time(), price)
            return {
                "price": price,
                "source": "promoklocki.pl",
                "url": f"{PROMOKLOCKI_BASE}/{set_number}"
            }

        # Fallback: klockoradar.pl
        price = await _fetch_klockoradar_price(session, set_number)
        if price:
            _price_cache[set_number] = (time.time(), price)
            return {
                "price": price,
                "source": "klockoradar.pl",
                "url": f"{KLOCKORADAR_BASE}/sets/{set_number}"
            }

        # No price found
        _price_cache[set_number] = (time.time(), None)
        return None

    finally:
        if close_session:
            await session.close()


async def compare_price(product_name: str, our_price: float, session: aiohttp.ClientSession = None) -> Optional[dict]:
    """
    Compare product price with market lowest.

    Args:
        product_name: Product name (must contain LEGO set number)
        our_price: Our price in PLN (float)
        session: Optional aiohttp session to reuse

    Returns:
        dict with keys: lowest, diff_pln, diff_pct, source, url
        or None if comparison not possible
    """
    set_number = extract_set_number(product_name)
    if not set_number:
        return None

    if not our_price or our_price <= 0:
        return None

    result = await get_lowest_price(set_number, session)
    if not result:
        return None

    lowest = result["price"]
    diff_pln = round(our_price - lowest, 2)
    diff_pct = round((our_price - lowest) / lowest * 100, 1) if lowest > 0 else 0

    return {
        "lowest": lowest,
        "diff_pln": diff_pln,
        "diff_pct": diff_pct,
        "source": result["source"],
        "url": result["url"],
        "set_number": set_number,
    }


def format_comparison(comparison: dict) -> str:
    """Format comparison result for Discord embed field."""
    if not comparison:
        return ""

    lowest = comparison["lowest"]
    diff_pln = comparison["diff_pln"]
    diff_pct = comparison["diff_pct"]
    source = comparison["source"]

    if diff_pln > 0:
        # Our price is higher
        emoji = "\U0001f534"  # red circle
        sign = "+"
    elif diff_pln < 0:
        # Our price is lower (deal!)
        emoji = "\U0001f7e2"  # green circle
        sign = ""
    else:
        emoji = "\u26aa"  # white circle
        sign = ""

    return (
        f"{emoji} Najniższa: **{lowest:.2f} zł** ({source})\n"
        f"Różnica: {sign}{diff_pln:.2f} zł ({sign}{diff_pct:.1f}%)"
    )


# --- Main (test) ---
if __name__ == "__main__":
    async def _test():
        test_cases = [
            ("LEGO Marvel Super Heroes 76345 Popiersie Doktora Dooma", 209.99),
            ("LEGO City 60412 Wóz strażacki 4x4", 189.99),
            ("LEGO Technic 42182 Motocykl", 99.99),
        ]
        async with aiohttp.ClientSession() as session:
            for name, price in test_cases:
                print(f"\n--- {name} (nasza cena: {price} zł) ---")
                result = await compare_price(name, price, session)
                if result:
                    print(f"  Najniższa: {result['lowest']} zł ({result['source']})")
                    print(f"  Różnica: {result['diff_pln']:+.2f} zł ({result['diff_pct']:+.1f}%)")
                    print(f"  URL: {result['url']}")
                    print(f"  Format: {format_comparison(result)}")
                else:
                    print("  Brak danych do porównania")

    asyncio.run(_test())
