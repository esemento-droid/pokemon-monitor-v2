"""
Strefa-TCG trigger for detector.py (BATCH MODE)
Collects all matching 30th products, then launches bot ONCE with all URLs.
Usage in detector.py:
  from strefatcg_trigger import check_strefatcg_trigger, flush_strefatcg_batch
  # On each product event:
  check_strefatcg_trigger(event_type, product)
  # After all events processed (end of detect_and_send):
  flush_strefatcg_batch()
"""

import asyncio
import json
import logging
import subprocess
from pathlib import Path

log = logging.getLogger("strefatcg_trigger")

BOT_PATH = Path("/opt/pokemon-monitor-v2/strefatcg_autobuy.py")
COMPLETED_FILE = Path("/opt/pokemon-monitor-v2/strefatcg_completed.json")
WEBHOOK_FILE = Path("/opt/pokemon-monitor-v2/discord_webhook_strefatcg.txt")
BASE_URL = "https://strefa-tcg.pl"

# Keywords that trigger the bot
KEYWORDS_30TH = ["30th", "30 celebration", "30-lecie", "30 lecie", "30 rocznica"]

# All 4 accounts
ALL_ACCOUNTS = [
    "esemento@gmail.com",
    "blackmat36@gmail.com",
    "tjbtaniojuzbylo@gmail.com",
    "y24015411@gmail.com",
]

# Batch collector (filled during detect_and_send, flushed at end)
_batch_products = []


def _load_completed():
    if COMPLETED_FILE.exists():
        return json.loads(COMPLETED_FILE.read_text())
    return {}


def _is_all_completed(product_id):
    """Check if all 4 accounts already bought this product."""
    completed = _load_completed()
    bought = completed.get(product_id, [])
    return all(acc in bought for acc in ALL_ACCOUNTS)


def _matches_keywords(name):
    name_lower = name.lower()
    return any(kw in name_lower for kw in KEYWORDS_30TH)


def check_strefatcg_trigger(event_type, product):
    """
    Checks if product matches 30th keywords and adds to batch.
    Called from detector.py on NEW_PRODUCT, RESTOCK, PRICE_CHANGE.
    """
    global _batch_products
    
    shop_name = product.get("shop", "")
    if shop_name != "strefa-tcg":
        return
    
    if not product.get("available", False):
        return
    
    name = product.get("name", "")
    product_id = product.get("id", "").replace("strefatcg_", "")
    url = product.get("url", "")
    
    if not url:
        url = f"{BASE_URL}/pl/p/product/{product_id}"
    
    # Check if already completed for all accounts
    if _is_all_completed(product_id):
        return
    
    # Must match 30th keywords
    if not _matches_keywords(name):
        return
    
    log.info(f"[STCG-TRIGGER] MATCH! event={event_type} name='{name}' id={product_id}")
    
    # Add to batch (avoid duplicates)
    if not any(p["url"] == url for p in _batch_products):
        _batch_products.append({"url": url, "name": name, "id": product_id, "price": product.get("price", "?")})


def flush_strefatcg_batch():
    """
    Called after detect_and_send finishes. If any products collected, launch bot once.
    """
    global _batch_products
    
    if not _batch_products:
        return
    
    products = _batch_products.copy()
    _batch_products = []
    
    log.info(f"[STCG-TRIGGER] Flushing batch: {len(products)} products")
    
    # Discord notify
    try:
        import aiohttp
        wh_url = WEBHOOK_FILE.read_text().strip() if WEBHOOK_FILE.exists() else ""
        if wh_url:
            product_lines = "\n".join([f"• {p['name']} ({p['price']})" for p in products])
            async def _notify():
                async with aiohttp.ClientSession() as s:
                    await s.post(wh_url, json={
                        "content": f"🚨 **STREFA-TCG TRIGGER** - {len(products)} produktów!\n{product_lines}\nOdpalam bota na 4 konta..."
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
        log.warning(f"[STCG-TRIGGER] Discord notify failed: {e}")
    
    # Launch bot with ALL product URLs
    if not BOT_PATH.exists():
        log.error(f"[STCG-TRIGGER] Bot not found: {BOT_PATH}")
        return
    
    urls = [p["url"] for p in products]
    cmd = [
        "/opt/pokemon-monitor-v2/venv/bin/python3", "-u",
        str(BOT_PATH),
        "--accounts", "4",
        "--qty", "1",
    ] + urls  # Multiple URLs as positional args
    
    env = dict(**__import__('os').environ, DISPLAY=":99")
    
    log.info(f"[STCG-TRIGGER] Launching bot with {len(urls)} products")
    try:
        subprocess.Popen(
            cmd,
            env=env,
            stdout=open("/opt/pokemon-monitor-v2/strefatcg_autobuy_stdout.log", "a"),
            stderr=open("/opt/pokemon-monitor-v2/strefatcg_autobuy_stderr.log", "a"),
            cwd="/opt/pokemon-monitor-v2"
        )
        log.info(f"[STCG-TRIGGER] Bot launched!")
    except Exception as e:
        log.error(f"[STCG-TRIGGER] Failed to launch bot: {e}")
