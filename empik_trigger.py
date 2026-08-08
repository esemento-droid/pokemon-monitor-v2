"""
Empik auto-buy trigger v2.
Fires on ANY event (NEW_PRODUCT, RESTOCK, PRICE_CHANGE, or just scan)
when: stock="empik" + available=True + pid in WATCH_PIDS + price <= max_price
"""
import subprocess
import json
import logging
from pathlib import Path

log = logging.getLogger("monitor")

# PIDs to watch: {pid: max_price}
WATCH_PIDS = {
    "1756071234": 160,  # First Partner Booster Collection 3
}

QTY = 3
MAX_ACCOUNTS = 20
COMPLETED_FILE = Path(__file__).parent / "empik_completed.json"
BOT_PATH = Path(__file__).parent / "empik_autobuy.py"
VENV_PYTHON = Path(__file__).parent / "venv" / "bin" / "python3"


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
    """Check if empik bot is already running."""
    import os
    lock = Path(__file__).parent / "empik_autobuy.lock"
    if lock.exists():
        pid = lock.read_text().strip()
        if os.path.exists(f"/proc/{pid}"):
            return True
        lock.unlink()
    return False


def check_empik_trigger(event_type, product):
    """Called from detector.py on ANY empik shop event."""
    # Check if this is empik-own
    if product.get("stock") != "empik":
        return

    # Check if available
    if not product.get("available"):
        return

    # Extract numeric PID
    pid = product.get("id", "").replace("empik_", "")
    if pid not in WATCH_PIDS:
        return

    # Check price
    max_price = WATCH_PIDS[pid]
    price = product.get("price", 0)
    if isinstance(price, str):
        price = float(price.replace(",", ".").replace("zł", "").strip())
    if price <= 0 or price > max_price:
        return

    url = product.get("url", "")
    if not url:
        return

    # Check if already ordered on all accounts
    if _all_accounts_done(url):
        log.info("[empik_trigger] All %d accounts done for %s, skip", MAX_ACCOUNTS, pid)
        return

    # Check if bot already running
    if _is_bot_running():
        log.info("[empik_trigger] Bot already running, skip")
        return

    log.info("[empik_trigger] TRIGGERED! pid=%s price=%.2f max=%d event=%s", pid, price, max_price, event_type)

    # Launch bot
    cmd = [
        str(VENV_PYTHON), "-u", str(BOT_PATH),
        "--qty", str(QTY),
        "--max", str(QTY * MAX_ACCOUNTS),
        url
    ]
    env = {"DISPLAY": ":99", "PATH": "/usr/bin:/bin"}
    try:
        proc = subprocess.Popen(
            cmd, env=env,
            stdout=open(str(Path(__file__).parent / "empik_autobuy_stdout.log"), "a"),
            stderr=open(str(Path(__file__).parent / "empik_autobuy_stderr.log"), "a"),
        )
        # Write lock
        lock = Path(__file__).parent / "empik_autobuy.lock"
        lock.write_text(str(proc.pid))
        log.info("[empik_trigger] Bot launched PID=%d", proc.pid)
        # Discord notification
        try:
            import requests as _req
            from config import DISCORD_WEBHOOK
            if DISCORD_WEBHOOK:
                _req.post(DISCORD_WEBHOOK, json={"content": f"🛒 **EMPIK BOT TRIGGERED!**\npid={pid} price={price:.2f}zł\n{url}"}, timeout=5)
        except: pass
    except Exception as e:
        log.error("[empik_trigger] Failed to launch: %s", e)
