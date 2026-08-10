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

# Specific products with qty ranges (min, max) — random per account
# Key: substring in product name (lowercase)
PRODUCT_QTY = {
    "elite trainer box": (1, 1),
    "tin - sylveon": (1, 3),
    "tin - greninja": (1, 3),
    "sticker collection - alolan": (1, 6),
    "sticker collection - lucario": (1, 6),
}

# Products to SKIP (not interested)
SKIP_KEYWORDS = ["binder", "2-pack", "poster", "ex box", "booster bundle"]

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


def _get_qty_for_product(name):
    """Get random qty for product based on PRODUCT_QTY config. Returns 0 if should skip."""
    name_lower = name.lower()

    # Skip unwanted products
    if any(skip in name_lower for skip in SKIP_KEYWORDS):
        return 0

    # Check specific products
    for keyword, (qty_min, qty_max) in PRODUCT_QTY.items():
        if keyword in name_lower:
            return random.randint(qty_min, qty_max)

    # Catch-all: any other 30th product (new/unknown) — buy 1
    return 1


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

    # Check if we want this product
    qty = _get_qty_for_product(name)
    if qty == 0:
        log.info(f"[TCGU-TRIGGER] SKIP (unwanted): '{name}'")
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
