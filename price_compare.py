"""
Price Compare Module — porównanie cen LEGO
Primary: promoklocki.pl/{set_number} (direct HTTP, no CF on product pages)
Fallback: klockoradar.pl (sitemap fuzzy match + JSON-LD lowPrice)

Promoklocki: gdy mamy numer zestawu -> szybki fetch jednej strony
Klockoradar: gdy nie mamy numeru -> fuzzy match nazwy po sitemap slugs
"""
import asyncio
import re
import json
import time
import logging
from typing import Optional

import aiohttp

logger = logging.getLogger("monitor")

# --- Cache ---
_sitemap_cache: dict = {}
_sitemap_last_fetch: float = 0
SITEMAP_TTL = 6 * 3600  # 6h

_price_cache: dict = {}
PRICE_TTL = 3600  # 1h

# --- Config ---
PROMOKLOCKI_BASE = "https://promoklocki.pl"
KLOCKORADAR_BASE = "https://klockoradar.pl"
SITEMAP_URLS = [f"{KLOCKORADAR_BASE}/sitemap/{i}.xml" for i in range(8)]
FLARESOLVERR_URL = "http://localhost:8191/v1"
FLARESOLVERR_TIMEOUT = 30000  # ms

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}

STOP_WORDS = {
    "lego", "the", "and", "with", "in", "of", "for", "to", "a", "an",
    "w", "i", "z", "do", "na", "od", "dla", "set", "r", "from"
}

# Regex to extract LEGO set number (4-6 digits)
SET_NUMBER_RE = re.compile(r'\b(\d{4,6})\b')

# Promoklocki price extraction
PROMOKLOCKI_PRICE_RE = re.compile(
    r'Aktualnie\s+najni[żz]sza\s+cena\s*([\d\s,.]+)\s*z[łl]',
    re.IGNORECASE
)
PROMOKLOCKI_PRICE_FALLBACK_RE = re.compile(
    r'"lowPrice"\s*:\s*"?([\d.,]+)"?',
    re.IGNORECASE
)


# ============================================================
# SET NUMBER EXTRACTION
# ============================================================

def extract_set_number(name: str) -> Optional[str]:
    """Extract LEGO set number (4-6 digits) from product name."""
    if not name:
        return None
    numbers = SET_NUMBER_RE.findall(name)
    if not numbers:
        return None
    # Prefer 5-digit (most common LEGO sets)
    for n in numbers:
        if len(n) == 5:
            return n
    for n in numbers:
        if len(n) == 6:
            return n
    for n in numbers:
        if len(n) == 4 and int(n) >= 1000:
            return n
    return numbers[0]


# ============================================================
# PROMOKLOCKI.PL (PRIMARY - when we have set number)
# ============================================================

def _parse_price_str(text: str) -> Optional[float]:
    """Parse Polish price string to float. '173,90' -> 173.90"""
    if not text:
        return None
    cleaned = text.strip().replace(" ", "").replace(",", ".")
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


async def _fetch_promoklocki_price(session: aiohttp.ClientSession, set_number: str) -> Optional[dict]:
    """Fetch lowest price from promoklocki.pl/{set_number} via FlareSolverr (CF bypass)."""
    url = f"{PROMOKLOCKI_BASE}/{set_number}"
    
    # Try FlareSolverr first (bypasses Cloudflare)
    try:
        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": FLARESOLVERR_TIMEOUT,
        }
        async with session.post(
            FLARESOLVERR_URL,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=35)
        ) as resp:
            if resp.status != 200:
                logger.warning(f"[PRICE] FlareSolverr HTTP {resp.status} for {set_number}")
                return None
            data = await resp.json()
            if data.get("status") != "ok":
                logger.warning(f"[PRICE] FlareSolverr status={data.get('status')} for {set_number}")
                return None
            html = data.get("solution", {}).get("response", "")
            if not html:
                return None
    except (aiohttp.ClientError, asyncio.TimeoutError, Exception) as e:
        logger.warning(f"[PRICE] FlareSolverr error for {set_number}: {e}")
        # Fallback: try direct (works if not CF blocked)
        try:
            async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text()
        except Exception:
            return None

    # Extract price from HTML
    price = None
    
    # Method 1: "Aktualnie najniższa cena" (JS-rendered, rare in raw HTML)
    match = PROMOKLOCKI_PRICE_RE.search(html)
    if match:
        price = _parse_price_str(match.group(1))

    # Method 2: JSON-LD lowPrice (always in raw HTML)
    if not price:
        match = PROMOKLOCKI_PRICE_FALLBACK_RE.search(html)
        if match:
            price = _parse_price_str(match.group(1))

    if not price:
        return None

    return {
        "set_number": set_number,
        "lowest_price": price,
        "shop": "promoklocki.pl",
        "shop_url": url,
        "offer_count": 0,
        "klockoradar_url": f"{KLOCKORADAR_BASE}/sets/{set_number}",
        "promoklocki_url": url,
        "source": "promoklocki.pl",
        "fetched_at": time.time(),
    }


# ============================================================
# KLOCKORADAR.PL (FALLBACK - fuzzy match from sitemap)
# ============================================================

async def _load_sitemap(session):
    """Load klockoradar sitemap: set_number -> slug mapping."""
    global _sitemap_cache, _sitemap_last_fetch
    if _sitemap_cache and (time.time() - _sitemap_last_fetch) < SITEMAP_TTL:
        return _sitemap_cache
    sets = {}
    for url in SITEMAP_URLS:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    continue
                xml = await resp.text()
            for m in re.findall(r'klockoradar\.pl/sets/(\d+)-([^<]+)</loc>', xml):
                sets[m[0]] = m[1]
        except Exception:
            continue
    if sets:
        _sitemap_cache = sets
        _sitemap_last_fetch = time.time()
        logger.info(f"[PRICE] Loaded {len(sets)} sets from klockoradar sitemap")
    return _sitemap_cache


def _normalize_name(name):
    """Normalize product name for fuzzy matching."""
    name = name.lower().replace("\u00ae", "").replace("(r)", "")
    name = re.sub(r'[^a-z0-9\s]', ' ', name)
    words = set(name.split()) - STOP_WORDS
    return {w for w in words if len(w) > 1}


def match_set_number(product_name, sitemap):
    """Fuzzy match product name against sitemap slugs. Returns set number or None."""
    name_words = _normalize_name(product_name)
    if not name_words:
        return None
    best_num = None
    best_score = 0
    for num, slug in sitemap.items():
        slug_words = set(slug.split('-')) - STOP_WORDS
        slug_words = {w for w in slug_words if len(w) > 1}
        score = len(name_words & slug_words)
        if score > best_score:
            best_score = score
            best_num = num
    return best_num if best_score >= 2 else None


async def _fetch_klockoradar_price(session, set_number):
    """Fetch price from klockoradar.pl via JSON-LD."""
    cached = _price_cache.get(f"kr_{set_number}")
    if cached and (time.time() - cached.get("fetched_at", 0)) < PRICE_TTL:
        return cached

    url = f"{KLOCKORADAR_BASE}/sets/{set_number}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15), headers=HEADERS) as resp:
            if resp.status != 200:
                return None
            html = await resp.text()
    except Exception:
        return None

    for ld_raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL):
        try:
            data = json.loads(ld_raw)
        except Exception:
            continue
        if data.get("@type") != "Product":
            continue
        offers = data.get("offers", {})
        if offers.get("@type") == "AggregateOffer":
            low = offers.get("lowPrice")
            if low is None:
                continue
            low = float(low)
            shop_name = ""
            shop_url = ""
            individual = offers.get("offers", [])
            if individual:
                cheapest = min(individual, key=lambda o: float(o.get("price", 99999)))
                shop_name = cheapest.get("seller", {}).get("name", "")
                shop_url = cheapest.get("url", "")
            result = {
                "set_number": set_number,
                "lowest_price": low,
                "shop": shop_name,
                "shop_url": shop_url,
                "offer_count": offers.get("offerCount", 0),
                "klockoradar_url": url,
                "promoklocki_url": f"{PROMOKLOCKI_BASE}/{set_number}",
                "source": "klockoradar.pl",
                "fetched_at": time.time(),
            }
            _price_cache[f"kr_{set_number}"] = result
            return result
    return None


# ============================================================
# MAIN API (backwards compatible)
# ============================================================

async def get_price_comparison(product_name: str, product_price: float, session=None) -> Optional[dict]:
    """
    Get price comparison for a LEGO product.
    
    Strategy:
    1. Try to extract set number from name -> promoklocki.pl (fastest, most accurate)
    2. If no number in name -> klockoradar fuzzy match via sitemap
    3. If promoklocki fails -> fallback to klockoradar for that set number
    
    Returns dict with: set_number, lowest_price, shop, difference, percentage, is_cheaper, etc.
    """
    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession(headers=HEADERS)

    try:
        price_data = None
        set_number = extract_set_number(product_name)

        if set_number:
            # Strategy 1: Direct promoklocki.pl fetch (fast!)
            cache_key = f"pk_{set_number}"
            cached = _price_cache.get(cache_key)
            if cached and (time.time() - cached.get("fetched_at", 0)) < PRICE_TTL:
                price_data = cached
            else:
                price_data = await _fetch_promoklocki_price(session, set_number)
                if price_data:
                    _price_cache[cache_key] = price_data

            # Fallback: klockoradar if promoklocki failed
            if not price_data:
                price_data = await _fetch_klockoradar_price(session, set_number)

        else:
            # Strategy 2: Fuzzy match via klockoradar sitemap
            sitemap = await _load_sitemap(session)
            if not sitemap:
                return None
            set_number = match_set_number(product_name, sitemap)
            if not set_number:
                return None

            # Try promoklocki first with matched number
            cache_key = f"pk_{set_number}"
            cached = _price_cache.get(cache_key)
            if cached and (time.time() - cached.get("fetched_at", 0)) < PRICE_TTL:
                price_data = cached
            else:
                price_data = await _fetch_promoklocki_price(session, set_number)
                if price_data:
                    _price_cache[cache_key] = price_data

            # Fallback to klockoradar
            if not price_data:
                price_data = await _fetch_klockoradar_price(session, set_number)

        if not price_data:
            return None

        lowest = price_data["lowest_price"]
        diff = product_price - lowest
        pct = (diff / lowest) * 100 if lowest > 0 else 0

        return {
            "set_number": price_data["set_number"],
            "lowest_price": lowest,
            "shop": price_data.get("shop", price_data.get("source", "")),
            "shop_url": price_data.get("shop_url", ""),
            "offer_count": price_data.get("offer_count", 0),
            "klockoradar_url": price_data.get("klockoradar_url", ""),
            "promoklocki_url": price_data.get("promoklocki_url", f"{PROMOKLOCKI_BASE}/{set_number}"),
            "source": price_data.get("source", ""),
            "difference": round(diff, 2),
            "percentage": round(pct, 1),
            "is_cheaper": diff < 0,
        }
    finally:
        if own_session:
            await session.close()


def format_price_comparison(comparison: dict) -> str:
    """Format comparison result for Discord embed field value."""
    if not comparison:
        return ""
    lowest = comparison["lowest_price"]
    diff = comparison["difference"]
    pct = comparison["percentage"]
    source = comparison.get("source", "")
    shop = comparison.get("shop", "")
    
    # Show source (promoklocki/klockoradar) + cheapest shop name if available
    if shop and shop != source and shop != "promoklocki.pl":
        price_info = f"{shop} ({lowest:.2f} zl) via {source}"
    else:
        price_info = f"{lowest:.2f} zl ({source})"

    if diff < 0:
        return f"\u2705 TANIEJ o {abs(diff):.2f} zl ({pct:.0f}%) | Najnizsza: {price_info}"
    elif diff > 0:
        return f"\u26a0\ufe0f DROZEJ o {diff:.2f} zl (+{pct:.0f}%) | Najnizsza: {price_info}"
    else:
        return f"\U0001f7f0 Taka sama cena | {price_info}"


# Aliases for backwards compatibility
compare_price = get_price_comparison
format_comparison = format_price_comparison


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    async def test():
        products = [
            # Z numerem zestawu (promoklocki direct)
            ("LEGO Marvel Super Heroes 76345 Popiersie Doktora Dooma", 209.99),
            ("LEGO City 60412 Wóz strażacki 4x4", 189.99),
            # Bez numeru (fuzzy match via klockoradar sitemap) - jak limango
            ("LEGO Technic Koenigsegg Jesko Absolut", 169.95),
            ("LEGO Icons Polaroid Onestep Sx 70", 189.95),
            ("LEGO Creator Sunflowers", 55.95),
        ]
        async with aiohttp.ClientSession(headers=HEADERS) as s:
            print("=== Price Compare Test ===\n")
            for name, price in products:
                r = await get_price_comparison(name, price, s)
                if r:
                    fmt = format_price_comparison(r)
                    print(f"  {name[:55]}")
                    print(f"    Nasza: {price} zl | Set #{r['set_number']} | Source: {r['source']}")
                    print(f"    {fmt}")
                    print(f"    URL: {r.get('promoklocki_url', r.get('klockoradar_url', ''))}")
                else:
                    print(f"  {name[:55]} -> BRAK DANYCH")
                print()

    asyncio.run(test())
