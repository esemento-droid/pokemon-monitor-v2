#!/usr/bin/env python3
"""
Price Cache — fetches lowest LEGO prices from klockoradar.pl (ALL sets).
Stores in JSON file. Limango reads from cache at scan time (instant compare).

WHY klockoradar (not promoklocki):
  - klockoradar: NO CF, direct HTTP, JSON-LD with lowPrice = fast bulk fetch
  - promoklocki: CF blocks everything except stealth browser = 1.5s/page = 5h for 12K sets
  - Both have same price data (aggregate from Polish shops)
  - Promoklocki URL still shown in Discord embed for user reference

Architecture:
  - Sitemap: 11,823 sets (klockoradar.pl/sitemap/*.xml)
  - Price fetch: direct HTTP GET + JSON-LD parse, 5 concurrent, ~20 min for all
  - Cache: data/price_cache.json (set_number → {lowest_price, shop, ...})
  - Limango: reads cache, fuzzy matches product name → set_number → compare

Usage:
  # Cron (2x/day):
  0 6,18 * * * cd /opt/pokemon-monitor-v2 && timeout 1800 ./venv/bin/python3 price_cache.py >> data/price_cache.log 2>&1

  # From limango scraper:
  from price_cache import get_cached_price
  data = get_cached_price("31136")  # Returns dict or None
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
KLOCKORADAR_BASE = "https://klockoradar.pl"
PROMOKLOCKI_BASE = "https://promoklocki.pl"
SITEMAP_URLS = [f"{KLOCKORADAR_BASE}/sitemap/{i}.xml" for i in range(8)]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}

# Concurrent fetches (polite but fast)
MAX_CONCURRENT = 5
DELAY_BETWEEN = 0.3  # seconds


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
    Cache valid 26h (refreshed 2x/day = every 12h, with grace period).
    """
    cache = load_cache()
    entry = cache.get(str(set_number))
    if not entry:
        return None
    updated = entry.get("updated_at_ts", 0)
    if time.time() - updated > 26 * 3600:
        return None
    return entry


async def load_sitemap(session: aiohttp.ClientSession) -> dict:
    """Load ALL set numbers from klockoradar sitemap. Returns {set_number: slug}."""
    sets = {}
    for url in SITEMAP_URLS:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    continue
                xml = await resp.text()
            for m in re.findall(r'klockoradar\.pl/sets/(\d+)-([^<]+)</loc>', xml):
                sets[m[0]] = m[1]
        except Exception as e:
            log.warning(f"Sitemap fetch failed ({url}): {e}")
            continue
    return sets


async def fetch_klockoradar_price(session: aiohttp.ClientSession, set_number: str, semaphore: asyncio.Semaphore) -> tuple:
    """
    Fetch lowest price for one set from klockoradar.pl.
    Returns (set_number, result_dict) or (set_number, None).
    """
    async with semaphore:
        url = f"{KLOCKORADAR_BASE}/sets/{set_number}"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return (set_number, None)
                html = await resp.text()
        except Exception:
            return (set_number, None)

        # Extract from JSON-LD
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
                try:
                    low = float(low)
                except (ValueError, TypeError):
                    continue
                if low <= 0:
                    continue

                # Cheapest shop name
                shop_name = ""
                individual = offers.get("offers", [])
                if individual:
                    try:
                        cheapest = min(individual, key=lambda o: float(o.get("price", 99999)))
                        shop_name = cheapest.get("seller", {}).get("name", "")
                    except Exception:
                        pass

                result = {
                    "set_number": set_number,
                    "lowest_price": low,
                    "shop": shop_name,
                    "promoklocki_url": f"{PROMOKLOCKI_BASE}/{set_number}",
                    "klockoradar_url": url,
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "updated_at_ts": time.time(),
                }
                await asyncio.sleep(DELAY_BETWEEN)
                return (set_number, result)

        await asyncio.sleep(DELAY_BETWEEN)
        return (set_number, None)


async def refresh_cache():
    """
    Refresh price cache — ALL sets from klockoradar sitemap.
    Direct HTTP, no CF, parallel fetch. ~20 min for 12K sets.
    """
    log.info("=== PRICE CACHE REFRESH START ===")

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Load sitemap (all 11K+ sets)
        sitemap = await load_sitemap(session)
        if not sitemap:
            log.error("Sitemap empty! Aborting.")
            return

        log.info(f"Sitemap loaded: {len(sitemap)} sets")

        # Save sitemap cache to disk (limango fuzzy match reads this)
        sitemap_cache_file = Path("/opt/pokemon-monitor-v2/data/sitemap_cache.json")
        try:
            sitemap_cache_file.write_text(json.dumps(sitemap, ensure_ascii=False))
            log.info(f"Sitemap cache saved: {len(sitemap)} sets -> {sitemap_cache_file}")
        except Exception as e:
            log.warning(f"Sitemap cache save failed: {e}")

        # Fetch prices for ALL sets
        set_numbers = list(sitemap.keys())
        log.info(f"Fetching prices for {len(set_numbers)} sets (max {MAX_CONCURRENT} concurrent)...")

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        cache = load_cache()

        # Process in batches of 500 (save progress, don't lose everything on crash)
        batch_size = 500
        total_ok = 0
        total_fail = 0

        for batch_start in range(0, len(set_numbers), batch_size):
            batch = set_numbers[batch_start:batch_start + batch_size]
            tasks = [fetch_klockoradar_price(session, sn, semaphore) for sn in batch]
            results = await asyncio.gather(*tasks)

            batch_ok = 0
            for set_num, data in results:
                if data:
                    cache[set_num] = data
                    batch_ok += 1

            total_ok += batch_ok
            total_fail += len(batch) - batch_ok

            # Save after each batch (crash-safe)
            save_cache(cache)
            log.info(f"  Batch {batch_start//batch_size + 1}: {batch_ok}/{len(batch)} OK | Total: {total_ok}/{batch_start + len(batch)}")

    log.info(f"=== PRICE CACHE REFRESH DONE: {total_ok} OK, {total_fail} failed, {len(cache)} total in cache ===")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [PRICE_CACHE] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    asyncio.run(refresh_cache())
