#!/usr/bin/env python3
"""
JapanCollectibles 30th Anniversary trigger (BATCH) - for individual products.
Catches everything with "30" in name EXCEPT Pakiet Celebracyjny (pid 9419).
Collects products into batch, launches bot ONCE with all URLs.

Integration in detector.py:
    from japancollectibles_30th_trigger import check_jc_30th_trigger, flush_jc_30th_batch
    # Per product:
    check_jc_30th_trigger(event_type, product)
    # After all events:
    flush_jc_30th_batch()
"""
import json
import logging
import subprocess
import os
from pathlib import Path

log = logging.getLogger(__name__)

BASE_DIR = Path("/opt/pokemon-monitor-v2")
COMPLETED_FILE = BASE_DIR / "japancollectibles_30th_completed.json"
BOT_PATH = BASE_DIR / "japancollectibles_autobuy_30th.py"

# Keywords to match
KEYWORDS = ["30"]

# Exclude - the main pakiet (handled by other bot)
EXCLUDE_PIDS = ["9419"]
EXCLUDE_KEYWORDS = ["pakiet"]

ACCOUNTS_EMAILS = [
    "esemento@gmail.com",
    "blackmat36@gmail.com",
    "tjbtaniojuzbylo@gmail.com",
    "y24015411@gmail.com",
]

# Batch collector
_batch = []  # list of (product_id, url, name)


def _load_completed():
    if COMPLETED_FILE.exists():
        try:
            return json.loads(COMPLETED_FILE.read_text())
        except Exception:
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
    raw_id = str(product.get("id", ""))
    if "_" in raw_id:
        return raw_id.split("_", 1)[1]
    return raw_id


def _matches(name, product_id):
    """Match 30th products but EXCLUDE pakiet celebracyjny."""
    name_lower = name.lower()
    pid = str(product_id)

    # Exclude specific PIDs (pakiet celebracyjny)
    if pid in EXCLUDE_PIDS:
        return False

    # Exclude by keyword (pakiet)
    if any(kw in name_lower for kw in EXCLUDE_KEYWORDS):
        return False

    # Must match 30th keywords
    return any(kw in name_lower for kw in KEYWORDS)


def check_jc_30th_trigger(event_type, product):
    """
    Called from detector.py. Adds matching products to batch.
    """
    global _batch

    shop = product.get("shop", "")
    if shop != "japancollectibles":
        return

    if event_type not in ("NEW_PRODUCT", "RESTOCK", "PRICE_CHANGE"):
        return

    name = product.get("name", "")
    available = product.get("available", False)
    url = product.get("url", "")
    product_id = _extract_product_id(product)

    if not available:
        return

    if not name or not product_id:
        return

    if _is_all_completed(product_id):
        return

    if not _matches(name, product_id):
        return

    # Check if already in batch
    if any(pid == product_id for pid, _, _ in _batch):
        return

    if not url:
        url = f"https://japancollectibles.shop/-p{product_id}"

    log.info(f"[JC-30TH] BATCH ADD: {event_type}: {name} (ID {product_id})")
    _batch.append((product_id, url, name))


def flush_jc_30th_batch():
    """
    Launch batch bot with all collected product URLs.
    Call AFTER all events for japancollectibles are processed.
    """
    global _batch
    if not _batch:
        return

    product_urls = [url for _, url, _ in _batch]
    names = [name for _, _, name in _batch]

    log.info(f"[JC-30TH] FLUSH BATCH: {len(_batch)} products")
    for pid, url, name in _batch:
        log.info(f"[JC-30TH]   - {name} ({pid})")

    # Discord notify
    try:
        import aiohttp, asyncio
        wh_file = BASE_DIR / "discord_webhook_jc.txt"
        if wh_file.exists():
            wh_url = wh_file.read_text().strip()
            if wh_url:
                names_str = "\n".join(f"  • {n}" for n in names)
                msg = f"🚨 **JC 30TH TRIGGER** {len(_batch)} produktów!\n{names_str}\nOdpalam batch bota na 4 konta..."
                async def _send():
                    async with aiohttp.ClientSession() as s:
                        await s.post(wh_url, json={"content": msg})
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(_send())
                    else:
                        loop.run_until_complete(_send())
                except Exception:
                    asyncio.run(_send())
    except Exception as e:
        log.warning(f"[JC-30TH] Discord notify failed: {e}")

    # Clear batch
    _batch = []

    # Launch bot
    if not BOT_PATH.exists():
        log.error(f"[JC-30TH] Bot not found: {BOT_PATH}")
        return

    cmd = [
        str(BASE_DIR / "venv" / "bin" / "python3"),
        str(BOT_PATH),
        "--accounts", "4",
        "--qty", "1",
    ] + product_urls

    env = os.environ.copy()
    env["DISPLAY"] = ":99"

    log.info(f"[JC-30TH] Launching batch bot: {len(product_urls)} URLs")
    try:
        subprocess.Popen(
            cmd,
            env=env,
            cwd=str(BASE_DIR),
            stdout=open(BASE_DIR / "japancollectibles_30th_stdout.log", "a"),
            stderr=open(BASE_DIR / "japancollectibles_30th_stderr.log", "a"),
        )
        log.info(f"[JC-30TH] Bot launched OK")
    except Exception as e:
        log.error(f"[JC-30TH] Failed to launch bot: {e}")
