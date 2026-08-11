"""
Media Expert auto-buy trigger.
Fires on NEW_PRODUCT, RESTOCK, or PRICE_CHANGE events
when: shop="mediaexpert" + available=True + pid in WATCH_PIDS + price <= max_price

Called from detector.py on every matching mediaexpert event.
"""
import subprocess
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("monitor")

# PIDs to watch: {pid: max_price_PLN}
# Add product IDs here when you want auto-buy
# PID = the numeric part from mediaexpert_XXXXX product id
WATCH_PIDS = {
    # "12345": 200,  # Example: Pokemon TCG Booster Box max 200 PLN
}

QTY = 3
MAX_ACCOUNTS = 20
COMPLETED_FILE = Path(__file__).parent / "mediaexpert_completed.json"
BOT_PATH = Path(__file__).parent / "mediaexpert_autobuy.py"
VENV_PYTHON = Path(__file__).parent / "venv" / "bin" / "python3"
LOCK_FILE = Path(__file__).parent / "mediaexpert_autobuy.lock"


def _load_completed():
    if COMPLETED_FILE.exists():
        return json.loads(COMPLETED_FILE.read_text())
    return {}


def _all_accounts_done(url):
    completed = _load_completed()
    done = 0
    for n in range(1, MAX_ACCOUNTS + 1):
        email = f"twanesek{n}@gmail.com"
        if url in completed.get(email, []):
            done += 1
    return done >= MAX_ACCOUNTS


def _is_bot_running():
    """Check if mediaexpert bot is already running."""
    if LOCK_FILE.exists():
        pid = LOCK_FILE.read_text().strip()
        if os.path.exists(f"/proc/{pid}"):
            return True
        LOCK_FILE.unlink()
    return False


def _extract_pid(product):
    """Extract numeric PID from product id field."""
    raw_id = product.get("id", "")
    # mediaexpert_12345 -> 12345
    pid = raw_id.replace("mediaexpert_", "")
    return pid


def _parse_price(product):
    """Parse price from product dict, return float or 0."""
    price = product.get("price", "")
    if not price or price == "brak":
        return 0.0
    if isinstance(price, (int, float)):
        return float(price)
    try:
        price_str = str(price).replace(",", ".").replace("\xa0", " ").strip()
        for suffix in ["zł", "PLN", "pln", "zl", "złotych"]:
            price_str = price_str.replace(suffix, "").strip()
        return float(price_str)
    except (ValueError, TypeError):
        return 0.0


def check_mediaexpert_trigger(event_type, product):
    """Called from detector.py on ANY mediaexpert shop event."""
    # Check if this is mediaexpert shop
    if product.get("shop") != "mediaexpert":
        return

    # Check if available
    if not product.get("available"):
        return

    # Extract PID
    pid = _extract_pid(product)
    if pid not in WATCH_PIDS:
        return

    # Check price
    max_price = WATCH_PIDS[pid]
    price = _parse_price(product)
    if price <= 0 or price > max_price:
        log.info("[mediaexpert_trigger] Price %.2f > max %d for pid=%s, skip", price, max_price, pid)
        return

    url = product.get("url", "")
    if not url:
        return

    # Check if already ordered on all accounts
    if _all_accounts_done(url):
        log.info("[mediaexpert_trigger] All %d accounts done for %s, skip", MAX_ACCOUNTS, pid)
        return

    # Check if bot already running
    if _is_bot_running():
        log.info("[mediaexpert_trigger] Bot already running, skip")
        return

    log.info("[mediaexpert_trigger] TRIGGERED! pid=%s price=%.2f max=%d event=%s", pid, price, max_price, event_type)

    # Launch bot
    cmd = [
        str(VENV_PYTHON), "-u", str(BOT_PATH),
        "--qty", str(QTY),
        "--max", str(QTY * MAX_ACCOUNTS),
        url
    ]
    env = {**os.environ, "DISPLAY": ":99"}
    try:
        proc = subprocess.Popen(
            cmd, env=env,
            stdout=open(str(Path(__file__).parent / "mediaexpert_autobuy_stdout.log"), "a"),
            stderr=open(str(Path(__file__).parent / "mediaexpert_autobuy_stderr.log"), "a"),
        )
        # Write lock
        LOCK_FILE.write_text(str(proc.pid))
        log.info("[mediaexpert_trigger] Bot launched PID=%d", proc.pid)

        # Discord notification
        try:
            import requests as _req
            wh_file = Path(__file__).parent / "discord_webhook_mediaexpert.txt"
            if wh_file.exists():
                wh_url = wh_file.read_text().strip()
                if wh_url:
                    _req.post(wh_url, json={
                        "content": f"🛒 **MEDIA EXPERT BOT TRIGGERED!**\npid={pid} price={price:.2f}zł event={event_type}\n{url}"
                    }, timeout=5)
        except Exception:
            pass
    except Exception as e:
        log.error("[mediaexpert_trigger] Failed to launch: %s", e)
