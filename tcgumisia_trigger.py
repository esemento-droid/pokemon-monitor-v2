"""
TCGumisia trigger for detector.py (BATCH MODE)
Specific 30th products with individual qty ranges.
Plus catch-all for any NEW 30th product not in the list.

Usage in detector.py:
  from tcgumisia_trigger import check_tcgumisia_trigger, flush_tcgumisia_batch
  check_tcgumisia_trigger(event_type, product)
  flush_tcgumisia_batch()
"""

import asyncio
import json
import logging
import os
import random
import subprocess
from pathlib import Path

log = logging.getLogger("tcgumisia_trigger")

BOT_PATH = Path("/opt/pokemon-monitor-v2/tcgumisia_autobuy.py")
COMPLETED_FILE = Path("/opt/pokemon-monitor-v2/tcgumisia_completed.json")
WEBHOOK_FILE = Path("/opt/pokemon-monitor-v2/discord_webhook_strefatcg.txt")

# Keywords that trigger the bot (any 30th product)
KEYWORDS_30TH = ["30th", "30 celebration", "30-lecie", "30 lecie", "30 rocznica"]

# Specific products with (qty_min, qty_max, max_price) — random qty per account
# Key: substring in product name (lowercase)
PRODUCT_CONFIG = {
    "elite trainer box": (2, 3, 375),
    "tin - sylveon": (2, 3, 145),
    "tin - greninja": (2, 3, 145),
    "sticker collection - alolan": (2, 6, 120),
    "sticker collection - lucario": (2, 6, 120),
    "booster bundle": (1, 4, 249),
    "ex box - greninja": (1, 4, 162),
    "ex box - sylveon": (1, 4, 162),
    "poster collection": (1, 3, 121),
    "2-pack": (1, 5, 81),
    "binder collection": (1, 1, 251),
}

# Products to SKIP (not interested)
SKIP_KEYWORDS = []

# All 4 accounts
ALL_ACCOUNTS = [
    "esemento@gmail.com",
    "blackmat36@gmail.com",
    "tjbtaniojuzbylo@gmail.com",
    "y24015411@gmail.com",
]

# Batch collector
_batch_products = []


def _load_completed():
    if COMPLETED_FILE.exists():
        try:
            return json.loads(COMPLETED_FILE.read_text())
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def _is_all_completed(product_id):
    completed = _load_completed()
    bought = completed.get(product_id, [])
    return all(acc in bought for acc in ALL_ACCOUNTS)


def _get_qty_for_product(name, price_str):
    """Get random qty for product based on PRODUCT_CONFIG. Returns 0 if should skip (price too high)."""
    name_lower = name.lower()

    # Parse price from string like "140.00 PLN" or "400,00"
    try:
        price_clean = price_str.replace("PLN", "").replace("zł", "").replace(",", ".").replace(" ", "").strip()
        price = float(price_clean)
    except (ValueError, TypeError):
        price = 9999  # If can't parse, skip (safety)

    # Check specific products
    for keyword, (qty_min, qty_max, max_price) in PRODUCT_CONFIG.items():
        if keyword in name_lower:
            if price < max_price:
                return random.randint(qty_min, qty_max)
            else:
                return 0  # Too expensive, skip

    # Catch-all: any other 30th product (new/unknown) — buy 1 if price < 500
    if price < 500:
        return 1
    return 0


def _matches_keywords(name):
    name_lower = name.lower()
    return any(kw in name_lower for kw in KEYWORDS_30TH)


def check_tcgumisia_trigger(event_type, product):
    """
    Check if product matches 30th keywords and add to batch.
    Called from detector.py on NEW_PRODUCT, RESTOCK, PRICE_CHANGE.
    """
    global _batch_products

    shop_name = product.get("shop", "")
    if shop_name != "tcgumisia.pl":
        return

    if not product.get("available", False):
        return

    name = product.get("name", "")
    url = product.get("url", "")

    if not url:
        return

    # Extract product ID
    import re
    slug = url.rstrip('/').split('/')[-1]
    slug = re.sub(r'/\d+$', '', slug)
    product_id = slug

    if _is_all_completed(product_id):
        return

    if not _matches_keywords(name):
        return

    # Check if we want this product (based on name + price)
    price_str = product.get("price", "9999")
    qty = _get_qty_for_product(name, price_str)
    if qty == 0:
        log.info(f"[TCGU-TRIGGER] SKIP (price/unwanted): '{name}' price={price_str}")
        return

    log.info(f"[TCGU-TRIGGER] MATCH! event={event_type} name='{name}' qty={qty}")

    if not any(p["url"] == url for p in _batch_products):
        _batch_products.append({
            "url": url,
            "name": name,
            "id": product_id,
            "price": product.get("price", "?"),
            "qty": qty,
        })


def flush_tcgumisia_batch():
    """Called after detect_and_send finishes. Launch bot if products collected."""
    global _batch_products

    if not _batch_products:
        return

    products = _batch_products.copy()
    _batch_products = []

    log.info(f"[TCGU-TRIGGER] Flushing batch: {len(products)} products")

    # Discord notify
    try:
        import aiohttp
        wh_url = WEBHOOK_FILE.read_text().strip() if WEBHOOK_FILE.exists() else ""
        if wh_url:
            product_lines = "\n".join([f"\u2022 {p['name']} (qty:{p['qty']}, {p['price']})" for p in products])
            async def _notify():
                async with aiohttp.ClientSession() as s:
                    await s.post(wh_url, json={
                        "content": f"\U0001f6a8 **TCGUMISIA TRIGGER** - {len(products)} produktów!\n{product_lines}\nOdpalam bota na 4 konta..."
                    })
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(_notify())
                else:
                    asyncio.run(_notify())
            except:
                pass
    except Exception as e:
        log.warning(f"[TCGU-TRIGGER] Discord notify failed: {e}")

    # Launch bot with --products-json
    if not BOT_PATH.exists():
        log.error(f"[TCGU-TRIGGER] Bot not found: {BOT_PATH}")
        return

    # Pass products as JSON (each with its own qty)
    products_json = json.dumps([{"url": p["url"], "qty": p["qty"]} for p in products])

    cmd = [
        "/opt/pokemon-monitor-v2/venv/bin/python3", "-u",
        str(BOT_PATH),
        "--products-json", products_json,
        "--accounts", "4",
    ]

    env = {**os.environ, "DISPLAY": ":99"}

    log.info(f"[TCGU-TRIGGER] Launching bot: {products_json}")
    try:
        subprocess.Popen(
            cmd,
            env=env,
            stdout=open("/opt/pokemon-monitor-v2/tcgumisia_autobuy_stdout.log", "a"),
            stderr=open("/opt/pokemon-monitor-v2/tcgumisia_autobuy_stderr.log", "a"),
            cwd="/opt/pokemon-monitor-v2"
        )
        log.info(f"[TCGU-TRIGGER] Bot launched!")
    except Exception as e:
        log.error(f"[TCGU-TRIGGER] Failed to launch bot: {e}")
