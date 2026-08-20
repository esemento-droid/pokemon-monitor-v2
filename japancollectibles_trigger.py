#!/usr/bin/env python3
"""
JapanCollectibles trigger for detector.py
Launches japancollectibles_autobuy.py when 30th anniversary products appear/restock.
"""
import json
import logging
import subprocess
import os
from pathlib import Path

log = logging.getLogger(__name__)

BASE_DIR = Path("/opt/pokemon-monitor-v2")
COMPLETED_FILE = BASE_DIR / "japancollectibles_completed.json"
BOT_PATH = BASE_DIR / "japancollectibles_torpedo.py"

# Keywords for 30th anniversary products
# Specific product IDs to watch
WATCH_PIDS = ["9419"]

# Keywords - must contain "pakiet" (catches "Pakiet Celebracyjny na 30-lecie")
KEYWORDS = ["pakiet"]

# Accounts
ACCOUNTS_EMAILS = [
    "esemento@gmail.com",
    "blackmat36@gmail.com",
    "tjbtaniojuzbylo@gmail.com",
    "y24015411@gmail.com",
]


def _load_completed():
    if COMPLETED_FILE.exists():
        try:
            return json.loads(COMPLETED_FILE.read_text())
        except:
            return {}
    return {}


def _is_all_completed(product_id):
    """Check if all 4 accounts already bought this product."""
    data = _load_completed()
    pid = str(product_id)
    if pid not in data:
        return False
    return len(data[pid]) >= len(ACCOUNTS_EMAILS)


def _extract_product_id(product):
    """Extract numeric product ID from scraper product dict."""
    # Format: japancollectibles_{id}
    raw_id = str(product.get("id", ""))
    if "_" in raw_id:
        return raw_id.split("_", 1)[1]
    return raw_id


def _matches_keywords(name, product_id):
    """Match by product ID OR keyword in name."""
    if str(product_id) in WATCH_PIDS:
        return True
    name_lower = name.lower()
    return any(kw in name_lower for kw in KEYWORDS)


def check_japancollectibles_trigger(event_type, product):
    """
    Called from detector.py on NEW_PRODUCT, RESTOCK, PRICE_CHANGE.
    Checks if product matches 30th keywords and launches bot.
    """
    shop = product.get("shop", "")
    if shop != "japancollectibles":
        return

    name = product.get("name", "")
    available = product.get("available", False)
    url = product.get("url", "")
    product_id = _extract_product_id(product)

    if not available:
        return

    if not name or not product_id:
        return

    # Check if already completed for all accounts
    if _is_all_completed(product_id):
        return

    # Must match specific PID or "pakiet" keyword
    if not _matches_keywords(name, product_id):
        return

    log.info(f"[JC-TRIGGER] MATCH! event={event_type} name='{name}' id={product_id} url={url}")

    # Discord notify about trigger
    try:
        import aiohttp, asyncio
        wh_file = BASE_DIR / "discord_webhook_jc.txt"
        if wh_file.exists():
            wh_url = wh_file.read_text().strip()
            if wh_url:
                async def _send():
                    async with aiohttp.ClientSession() as s:
                        await s.post(wh_url, json={"content": f"🚨 **TRIGGER** {event_type}: {name}\nCena: {product.get('price','?')}\nURL: {url}\nOdpalam bota na 4 konta..."})
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(_send())
                    else:
                        loop.run_until_complete(_send())
                except:
                    asyncio.run(_send())
    except Exception as e:
        log.warning(f"[JC-TRIGGER] Discord notify failed: {e}")

    # Fire TORPEDO DAEMON via trigger file (instant — daemon already has browser running)
    FIRE_FILE = Path("/tmp/jc_torpedo_fire.txt")
    log.info(f"[JC-TRIGGER] Writing trigger: product {product_id}")
    try:
        FIRE_FILE.write_text(str(product_id))
        log.info(f"[JC-TRIGGER] Torpedo daemon triggered for product {product_id}")
    except Exception as e:
        log.error(f"[JC-TRIGGER] Failed to write trigger file: {e}")
        # Fallback: launch torpedo as subprocess
        cmd = [
            str(BASE_DIR / "venv" / "bin" / "python3"),
            str(BASE_DIR / "jc_torpedo_daemon.py"),
            "--fire", str(product_id),
        ]
        env = os.environ.copy()
        env["DISPLAY"] = ":99"
        try:
            subprocess.Popen(cmd, env=env, cwd=str(BASE_DIR),
                stdout=open(BASE_DIR / "jc_torpedo_daemon.log", "a"),
                stderr=open(BASE_DIR / "jc_torpedo_daemon.log", "a"))
            log.info(f"[JC-TRIGGER] Fallback: launched daemon --fire {product_id}")
        except Exception as e2:
            log.error(f"[JC-TRIGGER] Fallback launch failed: {e2}")
