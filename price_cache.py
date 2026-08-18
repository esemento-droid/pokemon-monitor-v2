#!/usr/bin/env python3
"""
Price Cache — fetches lowest prices from promoklocki.pl 2x/day.
Uses patchright (stealth browser, headless=False) to bypass CF.
Stores in JSON file. Limango reads from cache at scan time (instant).

WHY patchright (not cf_bridge/FlareSolverr):
  - promoklocki CF blocks headless=True (cf_solver)
  - patchright headless=False + Xvfb passes CF every time
  - Runs standalone via cron (not part of monitor process)

Usage:
  # Cron (2x/day — 6:00 and 18:00):
  0 6,18 * * * cd /opt/pokemon-monitor-v2 && DISPLAY=:99 timeout 300 ./venv/bin/python3 price_cache.py >> data/price_cache.log 2>&1

  # From limango scraper:
  from price_cache import get_cached_price
  price = get_cached_price("75345")  # Returns dict or None
"""
import asyncio
import json
import re
import time
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

log = logging.getLogger("price_cache")

CACHE_FILE = Path("/opt/pokemon-monitor-v2/data/price_cache.json")
PROMOKLOCKI_BASE = "https://promoklocki.pl"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}

# Ensure DISPLAY for headless=False
if not os.environ.get("DISPLAY"):
    os.environ["DISPLAY"] = ":99"

# Price extraction regex
PRICE_RE = re.compile(r'najni.sza\s+cena.{0,200}?([\d]+[.,][\d]+)\s*z', re.IGNORECASE | re.DOTALL)
PRICE_FALLBACK_RE = re.compile(r'class="bprice"[^>]*>([\d]+[.,][\d]+)\s*z', re.IGNORECASE)


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
    Cache valid 14h (refreshed 2x/day = every 12h, with 2h grace).
    """
    cache = load_cache()
    entry = cache.get(str(set_number))
    if not entry:
        return None
    updated = entry.get("updated_at_ts", 0)
    if time.time() - updated > 14 * 3600:
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


async def fetch_prices_batch(set_numbers: list) -> dict:
    """
    Fetch lowest prices from promoklocki.pl using patchright stealth browser.
    Opens ONE browser, visits each set page sequentially (CF cookie persists).
    Returns dict: {set_number: {lowest_price, promoklocki_url, ...}}
    """
    from patchright.async_api import async_playwright

    results = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
            ]
        )
        context = await browser.new_context(user_agent=HEADERS["User-Agent"])
        page = await context.new_page()

        # First visit — solve CF challenge once
        log.info(f"Opening promoklocki.pl to solve CF...")
        try:
            await page.goto(f"{PROMOKLOCKI_BASE}/10330", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)

            # Wait for CF
            for _ in range(10):
                title = await page.title()
                if title and "moment" not in title.lower() and "checking" not in title.lower():
                    break
                await asyncio.sleep(2)

            title = await page.title()
            if not title or "moment" in title.lower():
                log.error("CF challenge failed — cannot access promoklocki.pl")
                await browser.close()
                return results

            log.info(f"CF passed! Fetching {len(set_numbers)} sets...")
        except Exception as e:
            log.error(f"Initial CF solve failed: {e}")
            await browser.close()
            return results

        # Now fetch each set (CF cookie persists in context)
        for i, set_num in enumerate(set_numbers):
            url = f"{PROMOKLOCKI_BASE}/{set_num}"
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(1.5)

                html = await page.content()
                if not html or len(html) < 500:
                    log.warning(f"  [{i+1}/{len(set_numbers)}] {set_num}: empty page")
                    continue

                # Extract price
                price = None
                match = PRICE_RE.search(html)
                if match:
                    price = _parse_price(match.group(1))
                if not price:
                    match = PRICE_FALLBACK_RE.search(html)
                    if match:
                        price = _parse_price(match.group(1))

                if price:
                    results[set_num] = {
                        "set_number": set_num,
                        "lowest_price": price,
                        "promoklocki_url": url,
                        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "updated_at_ts": time.time(),
                    }
                    log.info(f"  [{i+1}/{len(set_numbers)}] {set_num}: {price:.2f} zl")
                else:
                    log.warning(f"  [{i+1}/{len(set_numbers)}] {set_num}: no price found")

            except Exception as e:
                log.warning(f"  [{i+1}/{len(set_numbers)}] {set_num}: {e}")

            # Small delay between pages (polite, CF won't re-challenge)
            if i % 10 == 9:
                await asyncio.sleep(2)

        await browser.close()

    return results


async def refresh_cache():
    """
    Refresh price cache for all known set numbers.
    Uses patchright stealth browser — one session, CF solved once, all pages fetched fast.
    """
    log.info("=== PRICE CACHE REFRESH START ===")
    cache = load_cache()

    # Collect set numbers
    set_numbers = set()

    # Source 1: existing cache keys
    for key in cache:
        if re.match(r'^\d{4,6}$', key):
            set_numbers.add(key)

    # Source 2: limango products from DB
    sitemap = {}
    try:
        import aiohttp
        from database import get_shop_products, init_db
        await init_db()
        limango_products = await get_shop_products("limango")

        from price_compare import _load_sitemap, match_set_number, HEADERS as PC_HEADERS
        async with aiohttp.ClientSession(headers=PC_HEADERS) as s:
            sitemap = await _load_sitemap(s)

        for pid, prod in limango_products.items():
            name = prod.get("name", "")
            m = re.search(r'\b(\d{4,6})\b', name)
            if m:
                set_numbers.add(m.group(1))
            elif sitemap:
                matched = match_set_number(name, sitemap)
                if matched:
                    set_numbers.add(matched)
    except Exception as e:
        log.warning(f"DB/sitemap read failed: {e}")

    if not set_numbers:
        log.warning("No set numbers to refresh!")
        return

    # Save sitemap cache to disk
    if sitemap:
        sitemap_cache_file = Path("/opt/pokemon-monitor-v2/data/sitemap_cache.json")
        try:
            sitemap_cache_file.write_text(json.dumps(sitemap, ensure_ascii=False))
            log.info(f"Sitemap cache saved: {len(sitemap)} sets -> {sitemap_cache_file}")
        except Exception as e:
            log.warning(f"Sitemap cache save failed: {e}")

    log.info(f"Fetching prices for {len(set_numbers)} sets from promoklocki.pl (patchright)")

    # Fetch all via stealth browser
    results = await fetch_prices_batch(sorted(set_numbers))

    # Update cache
    for set_num, data in results.items():
        cache[set_num] = data

    save_cache(cache)
    log.info(f"=== PRICE CACHE REFRESH DONE: {len(results)} OK / {len(set_numbers)} total ===")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [PRICE_CACHE] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    asyncio.run(refresh_cache())
