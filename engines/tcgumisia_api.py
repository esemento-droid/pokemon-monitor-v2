"""
HYDRA v3 Engine: tcgumisia_api.py
=================================
Rapid product-level poller for tcgumisia.pl (Sellingo platform).

Strategy:
- Monitors a WATCHLIST of specific product URLs (not entire category)
- Uses regex instead of BeautifulSoup (10x lighter)
- Solves PoW ONCE and reuses cookies (~30 min lifetime)
- Polls every 3 seconds (vs 5-15s for old HTML scraper)
- Parallel async requests via asyncio.gather()
- Reports to detector.py using same product dict contract

This runs ALONGSIDE shops/tcgumisia.py (old scraper stays as fallback).
Whichever detects a restock FIRST triggers the bot.

Usage:
  Called from main.py as engine (see integration in engine_runner)
  Or standalone: python -m engines.tcgumisia_api
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import aiohttp

logger = logging.getLogger("engine.tcgumisia")

# ============================================================
# CONFIGURATION
# ============================================================

SHOP = "tcgumisia.pl"
BASE_URL = "https://tcgumisia.pl"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"

POLL_INTERVAL = 3  # seconds between full poll cycles
POW_REFRESH_INTERVAL = 1800  # re-solve PoW every 30 min
REQUEST_TIMEOUT = 10  # per-product request timeout
MAX_CONCURRENT = 5  # max parallel product requests

WATCHLIST_PATH = Path(__file__).parent / "tcgumisia_watchlist.json"

# Regex patterns for extracting data from product pages
RE_AVAILABILITY = re.compile(r'c-avaibility[^"]*?(--none)?', re.IGNORECASE)
RE_PRICE = re.compile(r'c-product__price-value[^>]*>\s*([\d\s,.]+)\s*(?:PLN|zł)', re.IGNORECASE)
RE_TITLE = re.compile(r'<h1[^>]*class="[^"]*c-product__title[^"]*"[^>]*>([^<]+)</h1>', re.IGNORECASE)
RE_IMAGE = re.compile(r'c-product__image[^>]*?(?:data-src|src)="([^"]+)"', re.IGNORECASE)
RE_STOCK_LABEL = re.compile(r'Niedostępny|Dostępny|Brak w magazynie|Produkt niedostępny', re.IGNORECASE)

# Regex for category page (faster than BS4)
RE_PRODUCT_BOX = re.compile(
    r'<div[^>]*class="[^"]*c-product-box[^"]*"[^>]*>.*?</div>\s*</div>\s*</div>',
    re.DOTALL | re.IGNORECASE
)
RE_BOX_TITLE = re.compile(r'c-product-box__title[^>]*>([^<]+)<', re.IGNORECASE)
RE_BOX_LINK = re.compile(r'<a[^>]*href="(https://tcgumisia\.pl/[^"]*?)"[^>]*>', re.IGNORECASE)
RE_BOX_PRICE = re.compile(r'c-product-box__price-value[^>]*>\s*([\d\s,.]+)\s*(?:PLN|zł)?', re.IGNORECASE)
RE_BOX_AVAIL = re.compile(r'c-avaibility(--none)?', re.IGNORECASE)
RE_BOX_IMAGE = re.compile(r'<img[^>]*(?:data-src|src)="([^"]+)"', re.IGNORECASE)

# PoW patterns
RE_POW_TOKEN = re.compile(r'token="([^"]+)"')
RE_POW_DIFF = re.compile(r'diff=(\d+)')

# Product filtering
EXCLUDE_KEYWORDS = [
    "lorcana", "one piece", "flesh and blood", "fab", "disney",
    "album", "sleeve", "koszulk", "binder", "toploader", "ultra pro",
    "ochraniacz", "plastikowy", "jpn", "(jpn", "deck", "pencil",
    "riftbound", "cyberpunk"
]


# ============================================================
# PoW SOLVER
# ============================================================

def solve_pow(token: str, diff: int) -> int:
    """Solve SHA-256 proof-of-work challenge (same as shops/tcgumisia.py)."""
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


# ============================================================
# ENGINE CLASS
# ============================================================

class TcgumisiaEngine:
    """Rapid-poll engine for tcgumisia.pl watchlist products."""

    def __init__(self):
        self.session: aiohttp.ClientSession | None = None
        self.pow_solved_at: float = 0
        self.watchlist: list[dict] = []
        self._last_states: dict[str, bool] = {}  # url -> available
        self._running = False

    def load_watchlist(self):
        """Load product watchlist from JSON file."""
        if not WATCHLIST_PATH.exists():
            logger.error(f"[ENGINE] Watchlist not found: {WATCHLIST_PATH}")
            return []

        try:
            data = json.loads(WATCHLIST_PATH.read_text())
            products = data.get("products", [])
            logger.info(f"[ENGINE] Loaded watchlist: {len(products)} products")
            return products
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"[ENGINE] Failed to load watchlist: {e}")
            return []

    async def ensure_session(self):
        """Create or refresh aiohttp session with solved PoW cookies."""
        now = time.time()

        if self.session and (now - self.pow_solved_at) < POW_REFRESH_INTERVAL:
            return True  # Session still valid

        # Close old session
        if self.session:
            await self.session.close()

        jar = aiohttp.CookieJar(unsafe=True)
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": USER_AGENT},
            cookie_jar=jar,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        )

        # Solve PoW challenge
        try:
            async with self.session.get(BASE_URL) as resp:
                html = await resp.text()

            if "Weryfikacja" not in html or "nodea" not in html:
                # No PoW needed (already solved or disabled)
                self.pow_solved_at = now
                logger.info("[ENGINE] No PoW needed, session ready")
                return True

            token_m = RE_POW_TOKEN.search(html)
            diff_m = RE_POW_DIFF.search(html)
            if not token_m or not diff_m:
                logger.error("[ENGINE] PoW: token/diff not found in HTML")
                return False

            token = token_m.group(1)
            diff = int(diff_m.group(1))

            logger.info(f"[ENGINE] Solving PoW (diff={diff})...")
            loop = asyncio.get_event_loop()
            nonce = await loop.run_in_executor(None, solve_pow, token, diff)

            data = {
                "token": token,
                "nonce": str(nonce),
                "fp": '{"wd":0,"lang":2,"hc":4,"ch":1,"gl":"none"}'
            }
            async with self.session.post(f"{BASE_URL}/__nodea/verify-js", data=data) as resp:
                j = await resp.json()
                if j.get("ok"):
                    self.pow_solved_at = now
                    logger.info(f"[ENGINE] PoW solved (nonce={nonce}), session ready")
                    return True
                else:
                    logger.error(f"[ENGINE] PoW verification failed: {j}")
                    return False

        except Exception as e:
            logger.error(f"[ENGINE] Session setup error: {e}")
            if self.session:
                await self.session.close()
                self.session = None
            return False

    async def poll_product(self, product: dict) -> dict | None:
        """
        Poll a single product URL and return product dict.
        Returns None on error (will be skipped in results).
        """
        url = product["url"]
        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(f"[ENGINE] HTTP {resp.status} for {url}")
                    return None
                html = await resp.text()

            # Check if PoW challenge appeared (session expired)
            if "Weryfikacja" in html and "nodea" in html:
                logger.warning("[ENGINE] PoW expired mid-session, marking for refresh")
                self.pow_solved_at = 0  # Force refresh next cycle
                return None

            # Extract availability via regex (FAST)
            # Look for availability indicator
            available = True
            if "Niedostępny" in html or "Brak w magazynie" in html or "Produkt niedostępny" in html:
                available = False
            elif "Dostępny" in html:
                available = True
            else:
                # Fallback: check c-avaibility--none class
                avail_match = RE_AVAILABILITY.search(html)
                if avail_match and avail_match.group(1):
                    available = False

            # Extract price
            price = "brak"
            price_match = RE_PRICE.search(html)
            if price_match:
                price_raw = price_match.group(1).replace(" ", "").replace(",", ".").strip()
                try:
                    price = f"{float(price_raw):.2f} PLN"
                except ValueError:
                    price = price_raw + " PLN"

            # Generate stable ID (same format as shops/tcgumisia.py)
            # URL: https://tcgumisia.pl/slug/category_id → id = "tcgumisia_slug"
            url_clean = re.sub(r'/\d+$', '', url.rstrip("/"))
            slug = url_clean.replace("https://tcgumisia.pl/", "").replace("/", "_")
            pid = f"tcgumisia_{slug}"

            # Use watchlist name or extract from HTML
            name = product.get("name", "")
            if not name:
                title_match = RE_TITLE.search(html)
                if title_match:
                    name = title_match.group(1).strip()
                else:
                    name = slug.replace("-", " ").title()

            # Image (optional, not critical for detection)
            image = ""
            img_match = RE_IMAGE.search(html)
            if img_match:
                image = img_match.group(1)

            return {
                "id": pid,
                "name": name,
                "price": price,
                "shop": SHOP,
                "url": url_clean,
                "image": image,
                "stock": 1 if available else 0,
                "available": available,
            }

        except asyncio.TimeoutError:
            logger.warning(f"[ENGINE] Timeout polling {url}")
            return None
        except Exception as e:
            logger.error(f"[ENGINE] Error polling {url}: {e}")
            return None

    async def poll_category(self, category_url: str) -> list[dict]:
        """
        Rapid category poll using regex (no BeautifulSoup).
        Used as secondary method to discover NEW products not in watchlist.
        """
        try:
            async with self.session.get(
                f"{BASE_URL}{category_url}",
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()

            if "Weryfikacja" in html and "nodea" in html:
                self.pow_solved_at = 0
                return []

            products = []
            seen_ids = set()

            # Split by product boxes using a simpler approach
            # Find all product box sections
            boxes = html.split('c-product-box"')

            for box_html in boxes[1:]:  # Skip first (before first product)
                # Cut at next product box
                box_html = box_html[:box_html.find('c-product-box"')] if 'c-product-box"' in box_html else box_html[:5000]

                # Extract title
                title_match = RE_BOX_TITLE.search(box_html)
                if not title_match:
                    continue
                name = title_match.group(1).strip()

                # Filter excluded keywords
                if any(kw in name.lower() for kw in EXCLUDE_KEYWORDS):
                    continue

                # Extract link
                link_match = RE_BOX_LINK.search(box_html)
                if not link_match:
                    continue
                href = link_match.group(1)
                if "koszyk" in href:
                    continue

                # Clean URL
                href_clean = re.sub(r'/\d+$', '', href.rstrip("/"))
                slug = href_clean.replace("https://tcgumisia.pl/", "").replace("/", "_")
                pid = f"tcgumisia_{slug}"

                if pid in seen_ids:
                    continue
                seen_ids.add(pid)

                # Availability
                available = "--none" not in box_html.split("c-avaibility")[1][:20] if "c-avaibility" in box_html else True

                # Price
                price = "brak"
                price_match = RE_BOX_PRICE.search(box_html)
                if price_match:
                    price_raw = price_match.group(1).replace(" ", "").replace(",", ".").strip()
                    try:
                        price = f"{float(price_raw):.2f} PLN"
                    except ValueError:
                        price = price_raw + " PLN"

                # Image
                image = ""
                img_match = RE_BOX_IMAGE.search(box_html)
                if img_match:
                    image = img_match.group(1)

                products.append({
                    "id": pid,
                    "name": name,
                    "price": price,
                    "shop": SHOP,
                    "url": href_clean,
                    "image": image,
                    "stock": 1 if available else 0,
                    "available": available,
                })

            return products

        except Exception as e:
            logger.error(f"[ENGINE] Category poll error: {e}")
            return []

    async def get_products(self) -> list[dict]:
        """
        Main entry point - matches shops/*.py contract.
        Polls watchlist products in parallel + category scan.
        Returns combined unique product list.
        """
        # Ensure we have a valid session
        if not await self.ensure_session():
            return []

        # Load/reload watchlist
        self.watchlist = self.load_watchlist()

        # Poll watchlist products in parallel (capped concurrency)
        sem = asyncio.Semaphore(MAX_CONCURRENT)

        async def _poll_with_sem(product):
            async with sem:
                return await self.poll_product(product)

        # Parallel poll watchlist
        tasks = [_poll_with_sem(p) for p in self.watchlist]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        products = []
        seen_ids = set()
        for r in results:
            if isinstance(r, dict) and r is not None:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    products.append(r)

        # Also do a quick category scan to catch NEW products
        for cat in ["/pokemon", "/pre-order"]:
            cat_products = await self.poll_category(cat)
            for p in cat_products:
                if p["id"] not in seen_ids:
                    seen_ids.add(p["id"])
                    products.append(p)

        logger.info(f"[ENGINE] Poll complete: {len(products)} products ({len(self.watchlist)} watchlist + category)")
        return products

    async def close(self):
        """Cleanup."""
        if self.session:
            await self.session.close()
            self.session = None


# ============================================================
# MODULE-LEVEL INTERFACE (compatible with main.py shop_worker)
# ============================================================

_engine = TcgumisiaEngine()


async def get_products() -> list[dict]:
    """
    Drop-in replacement for shops/tcgumisia.py get_products().
    Same contract: returns list of product dicts.
    """
    return await _engine.get_products()


# ============================================================
# STANDALONE MODE (for testing)
# ============================================================

async def _standalone():
    """Run engine standalone for testing."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    engine = TcgumisiaEngine()
    try:
        products = await engine.get_products()
        print(f"\n{'='*60}")
        print(f"RESULTS: {len(products)} products")
        print(f"{'='*60}")

        available_count = sum(1 for p in products if p["available"])
        unavailable_count = len(products) - available_count

        print(f"  Available: {available_count}")
        print(f"  Unavailable: {unavailable_count}")
        print()

        for p in sorted(products, key=lambda x: (not x["available"], x["name"])):
            status = "AVAILABLE" if p["available"] else "---"
            print(f"  [{status:9}] {p['price']:>12} | {p['name'][:60]}")

    finally:
        await engine.close()


if __name__ == "__main__":
    asyncio.run(_standalone())
