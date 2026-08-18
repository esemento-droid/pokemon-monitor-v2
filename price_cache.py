#!/usr/bin/env python3
"""
Price Cache — fetches lowest prices from promoklocki.pl every 4h.
Stores in JSON file. Limango reads from cache (instant, no FlareSolverr at scan time).

Usage:
  # Cron (every 4h):
  0 */4 * * * cd /opt/pokemon-monitor-v2 && ./venv/bin/python3 price_cache.py >> data/price_cache.log 2>&1

  # From limango scraper:
  from price_cache import get_cached_price
  price = get_cached_price("75345")  # Returns float or None
"""
import asyncio
import json
import re
import time
import logging
import sys
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).parent))

log = logging.getLogger("price_cache")

CACHE_FILE = Path("/opt/pokemon-monitor-v2/data/price_cache.json")
FLARESOLVERR_URL = "http://localhost:8191/v1"
PROMOKLOCKI_BASE = "https://promoklocki.pl"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}

# Price extraction regex
PRICE_RE = re.compile(r'Aktualnie\s+najni[żz]sza\s+cena\s*([\d\s,.]+)\s*z[łl]', re.IGNORECASE)
PRICE_FALLBACK_RE = re.compile(r'"lowPrice"\s*:\s*"?([\d.,]+)"?', re.IGNORECASE)
# Shop name extraction
SHOP_RE = re.compile(r'<a[^>]*class="[^"]*lowest[^"]*"[^>]*>(.*?)</a>', re.DOTALL)


def load_cache() -> dict:
    """Load price cache from file."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_cache(cache: dict):
    """Save price cache to file."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False))


def get_cached_price(set_number: str) -> dict | None:
    """
    Get cached price for a set number. Returns dict or None.
    Dict: {"lowest_price": float, "shop": str, "updated_at": str, "promoklocki_url": str}
    """
    cache = load_cache()
    entry = cache.get(str(set_number))
    if not entry:
        return None
    # Cache valid for 6h (generous — refreshed every 4h)
    updated = entry.get("updated_at_ts", 0)
    if time.time() - updated > 6 * 3600:
        return None
    return entry


def _parse_price(text: str) -> float | None:
    """Parse Polish price string."""
    if not text:
        return None
    cleaned = text.strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


async def fetch_promoklocki_price(session: aiohttp.ClientSession, set_number: str) -> dict | None:
    """Fetch lowest price from promoklocki.pl via FlareSolverr."""
    url = f"{PROMOKLOCKI_BASE}/{set_number}"
    try:
        payload = {
            "cmd": "request.get",
            "url": url,
            "session": "price_cache",
            "maxTimeout": 30000,
        }
        async with session.post(
            FLARESOLVERR_URL,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=35)
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            if data.get("status") != "ok":
                return None
            html = data.get("solution", {}).get("response", "")
            if not html:
                return None
    except Exception as e:
        log.warning(f"[{set_number}] FS error: {e}")
        return None

    # Extract price
    price = None
    match = PRICE_RE.search(html)
    if match:
        price = _parse_price(match.group(1))
    if not price:
        match = PRICE_FALLBACK_RE.search(html)
        if match:
            price = _parse_price(match.group(1))
    if not price:
        return None

    return {
        "set_number": set_number,
        "lowest_price": price,
        "promoklocki_url": url,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at_ts": time.time(),
    }


async def refresh_cache():
    """
    Refresh price cache for all known set numbers.
    Fetches from promoklocki.pl via FlareSolverr, one at a time with delay.
    """
    log.info("=== PRICE CACHE REFRESH START ===")
    cache = load_cache()

    # Collect set numbers from limango products in DB
    set_numbers = set()

    # Source 1: existing cache keys
    for key in cache:
        if re.match(r'^\d{4,6}$', key):
            set_numbers.add(key)

    # Source 2: limango products from DB — extract set numbers from names + fuzzy match
    try:
        from database import get_shop_products, init_db
        await init_db()
        limango_products = await get_shop_products("limango")

        # Load klockoradar sitemap for fuzzy name→number matching
        from price_compare import _load_sitemap, match_set_number, HEADERS as PC_HEADERS
        sitemap = {}
        async with aiohttp.ClientSession(headers=PC_HEADERS) as s:
            sitemap = await _load_sitemap(s)

        for pid, prod in limango_products.items():
            name = prod.get("name", "")
            # Direct: extract 5-digit number from name
            m = re.search(r'\b(\d{5})\b', name)
            if m:
                set_numbers.add(m.group(1))
            # Fuzzy: match name to klockoradar sitemap slugs
            elif sitemap:
                matched = match_set_number(name, sitemap)
                if matched:
                    set_numbers.add(matched)
    except Exception as e:
        log.warning(f"DB/sitemap read failed: {e}")

    if not set_numbers:
        log.warning("No set numbers to refresh!")
        return

    log.info(f"Refreshing prices for {len(set_numbers)} sets")

    # Create FlareSolverr session (reuse = faster)
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        try:
            await session.post(FLARESOLVERR_URL, json={"cmd": "sessions.create", "session": "price_cache"}, timeout=aiohttp.ClientTimeout(total=10))
        except Exception:
            pass

        success = 0
        failed = 0
        for i, set_num in enumerate(sorted(set_numbers)):
            result = await fetch_promoklocki_price(session, set_num)
            if result:
                cache[set_num] = result
                success += 1
                log.info(f"  [{i+1}/{len(set_numbers)}] {set_num}: {result['lowest_price']:.2f} zl")
            else:
                failed += 1
                log.warning(f"  [{i+1}/{len(set_numbers)}] {set_num}: FAILED")

            # Delay between requests (don't overwhelm FS)
            await asyncio.sleep(5)

        # Destroy session
        try:
            await session.post(FLARESOLVERR_URL, json={"cmd": "sessions.destroy", "session": "price_cache"}, timeout=aiohttp.ClientTimeout(total=5))
        except Exception:
            pass

    save_cache(cache)
    log.info(f"=== PRICE CACHE REFRESH DONE: {success} OK, {failed} failed, {len(cache)} total in cache ===")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [PRICE_CACHE] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    asyncio.run(refresh_cache())
