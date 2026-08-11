"""
HYDRA v3 Engine: tcgumisia_api.py
=================================
Rapid category poller for tcgumisia.pl (Sellingo platform).

Strategy:
- Scans /pokemon and /pre-order every 3 seconds
- Uses regex instead of BeautifulSoup (10x lighter parsing)
- Solves PoW ONCE and reuses cookies (~30 min lifetime)
- Monitors ALL sealed Pokemon TCG products (not just 30th)
- Reports to detector.py using same product dict contract

This runs ALONGSIDE shops/tcgumisia.py (old scraper stays as fallback).
Whichever detects a restock or new drop FIRST triggers the bot.

Filters:
- ONLY English sealed products (booster boxes, ETBs, tins, collections, bundles)
- EXCLUDES: decks, singles, Japanese, accessories, sleeves, playmats, albums

Usage:
  Called from main.py as engine (via engine_runner)
  Or standalone: python -m engines.tcgumisia_api
"""

import asyncio
import hashlib
import logging
import os
import re
import sys
import time

import aiohttp

# Ensure parent dir is in path for config imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.product_filter import should_exclude

logger = logging.getLogger("engine.tcgumisia")

# ============================================================
# CONFIGURATION
# ============================================================

SHOP = "tcgumisia.pl"
BASE_URL = "https://tcgumisia.pl"
CATEGORY_URLS = ["/pokemon", "/pre-order"]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"

POLL_INTERVAL = 3  # seconds between full poll cycles
POW_REFRESH_INTERVAL = 1800  # re-solve PoW every 30 min
REQUEST_TIMEOUT = 20  # per-request timeout

# For /pre-order page — only include Pokemon products (other games filtered out by central exclude)
POKEMON_KEYWORDS = ["pokemon", "pokémon", "pikachu", "charizard", "booster", "etb", "trainer box"]

# Regex patterns for category page parsing (replaces BeautifulSoup)
RE_BOX_TITLE = re.compile(r'c-product-box__title[^>]*>([^<]+)<', re.IGNORECASE)
RE_BOX_LINK = re.compile(r'<a[^>]*href="(https://tcgumisia\.pl/[^"]*?)"[^>]*>', re.IGNORECASE)
RE_BOX_PRICE = re.compile(r'c-product-box__price-value[^>]*>\s*([\d\s,.]+)', re.IGNORECASE)
RE_BOX_IMAGE = re.compile(r'<img[^>]*(?:data-src|src)="([^"]+)"', re.IGNORECASE)

# PoW patterns
RE_POW_TOKEN = re.compile(r'token="([^"]+)"')
RE_POW_DIFF = re.compile(r'diff=(\d+)')


# ============================================================
# PoW SOLVER
# ============================================================

def solve_pow(token: str, diff: int) -> int:
    """Solve SHA-256 proof-of-work challenge."""
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
    """Rapid category poller for tcgumisia.pl — all sealed Pokemon products."""

    def __init__(self):
        self.session: "aiohttp.ClientSession | None" = None
        self.pow_solved_at: float = 0

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

    async def poll_category(self, category_url: str) -> list[dict]:
        """
        Rapid category poll using regex (no BeautifulSoup).
        Returns list of product dicts.
        """
        url = BASE_URL + category_url
        is_preorder = "pre-order" in category_url

        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(f"[ENGINE] HTTP {resp.status} for {url}")
                    return []
                html = await resp.text()

            # Check if PoW expired
            if "Weryfikacja" in html and "nodea" in html:
                logger.warning("[ENGINE] PoW expired, marking for refresh")
                self.pow_solved_at = 0
                return []

            products = []
            seen_ids = set()

            # Split HTML by product box titles (reliable anchor point)
            # Each chunk starts right after "c-product-box__title" 
            # Format: ...c-product-box__title">Product Name</span>...
            chunks = html.split('c-product-box__title')

            for chunk in chunks[1:]:  # Skip first chunk (before first product)
                # Limit chunk size — each product block is ~2-3KB
                chunk = chunk[:4000]

                # Extract title — right at the start of chunk: ...">Name</...
                title_match = re.search(r'[^>]*>([^<]+)<', chunk)
                if not title_match:
                    continue
                name = title_match.group(1).strip()
                if not name or len(name) < 3:
                    continue

                # Filter: exclude unwanted products (central exclude list)
                if should_exclude(name):
                    continue

                # Filter: pre-order page — only Pokemon products
                if is_preorder:
                    if not any(kw in name.lower() for kw in POKEMON_KEYWORDS):
                        continue

                # Extract link
                link_match = RE_BOX_LINK.search(chunk)
                if not link_match:
                    continue
                href = link_match.group(1)
                if "koszyk" in href:
                    # Try next link
                    for m in RE_BOX_LINK.finditer(chunk):
                        if "koszyk" not in m.group(1):
                            href = m.group(1)
                            break
                    else:
                        continue

                # Clean URL — remove trailing /category_id
                href_clean = re.sub(r'/\d+$', '', href.rstrip("/"))
                slug = href_clean.replace("https://tcgumisia.pl/", "").replace("/", "_")
                pid = f"tcgumisia_{slug}"

                if not pid or pid == "tcgumisia_" or pid in seen_ids:
                    continue
                seen_ids.add(pid)

                # Availability — check for c-avaibility--none
                available = True
                if "c-avaibility--none" in chunk or "Niedostępny" in chunk:
                    available = False

                # Price
                price = "brak"
                price_match = RE_BOX_PRICE.search(chunk)
                if price_match:
                    price_raw = price_match.group(1).replace(" ", "").replace(",", ".").strip()
                    try:
                        price = f"{float(price_raw):.2f} PLN"
                    except ValueError:
                        price = price_raw + " PLN"

                # Image
                image = ""
                img_match = RE_BOX_IMAGE.search(chunk)
                if img_match:
                    img_url = img_match.group(1)
                    # Skip tiny placeholder images
                    if "blank" not in img_url and len(img_url) > 10:
                        image = img_url

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

        except asyncio.TimeoutError:
            logger.warning(f"[ENGINE] Timeout for {url}")
            return []
        except Exception as e:
            logger.error(f"[ENGINE] Error polling {url}: {e}")
            return []

    async def get_products(self) -> list[dict]:
        """
        Main entry point — matches shops/*.py contract.
        Scans all category pages and returns combined product list.
        """
        if not await self.ensure_session():
            return []

        all_products = []
        seen_ids = set()

        for cat_url in CATEGORY_URLS:
            cat_products = await self.poll_category(cat_url)
            for p in cat_products:
                if p["id"] not in seen_ids:
                    seen_ids.add(p["id"])
                    all_products.append(p)

        if all_products:
            logger.info(f"[ENGINE] {len(all_products)} products from {len(CATEGORY_URLS)} categories")

        return all_products

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
            status = "AVAIL" if p["available"] else "---"
            print(f"  [{status:5}] {p['price']:>12} | {p['name'][:60]}")
            print(f"          ID: {p['id']}")

    finally:
        await engine.close()


if __name__ == "__main__":
    asyncio.run(_standalone())
