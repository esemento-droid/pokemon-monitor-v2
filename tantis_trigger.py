"""
Tantis auto-buy trigger - called from detector.py on NEW_PRODUCT/RESTOCK events.
Triggers tantis_autobuy.py for matching products.

BATCH MODE: collects all matching products during a scan cycle,
then launches bot ONCE with all product IDs (1 cart, 1 order).

Integration in detector.py:
    from tantis_trigger import check_tantis_trigger, flush_tantis_batch
    # After detect_and_send(), call per product:
    check_tantis_trigger(event_type, product)
    # After ALL events processed (end of detect_and_send):
    flush_tantis_batch()
"""

import subprocess
import os
import re
import json
import logging

log = logging.getLogger("tantis_trigger")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_PATH = os.path.join(BASE_DIR, "tantis_autobuy.py")
PYTHON = os.path.join(BASE_DIR, "venv", "bin", "python3")
COMPLETED_FILE = os.path.join(BASE_DIR, "tantis_completed.json")

# Trigger rules: list of (keyword, max_price, qty) tuples
# If max_price is None, no price limit
TRIGGER_RULES = [
    ("first partner 3", 160.0, 2),
    ("first partner booster collection 3", 160.0, 2),
    ("30th", None, 1),
    ("30 ", None, 1),
    ("30-lecie", None, 1),
    ("30 lecie", None, 1),
    ("30 rocznica", None, 1),
    ("anniversary", None, 1),
    ("celebration", None, 1),
]

# Batch collector - accumulates products during scan cycle
_batch = []  # list of (product_id, name, qty)


def load_completed() -> dict:
    """Load completed purchases {product_id: [account_emails]}."""
    try:
        if os.path.exists(COMPLETED_FILE):
            with open(COMPLETED_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def is_tantis_completed(product_id: str) -> bool:
    """Check if product was already bought on all 4 accounts."""
    data = load_completed()
    buyers = data.get(str(product_id), [])
    return len(buyers) >= 4


def extract_product_id(product_id: str) -> str:
    """Extract numeric tantis product ID from monitor ID format (tantis_iXXXXXXX or tantis_XXXXXXX)."""
    match = re.search(r'(\d{5,})', product_id)
    if match:
        return match.group(1)
    return None


def parse_price(price_str: str) -> float:
    """Parse price string to float."""
    if not price_str or price_str == "brak":
        return 0.0
    match = re.search(r'(\d+[,.]?\d*)', str(price_str))
    if match:
        return float(match.group(1).replace(",", "."))
    return 0.0


def should_trigger(product: dict):
    """Check if product matches trigger conditions. Returns (True, qty) or (False, 0)."""
    name = (product.get("name") or "").lower()
    shop = (product.get("shop") or "").lower()
    available = product.get("available", False)
    price = parse_price(product.get("price", ""))

    # Must be tantis shop
    if shop != "tantis":
        return False, 0

    # Must be available
    if not available:
        return False, 0

    # Check each trigger rule
    for keyword, max_price, qty in TRIGGER_RULES:
        if keyword in name:
            # Check price limit for this rule
            if max_price is not None and price > max_price and price > 0:
                log.info(f"[tantis_trigger] Skipping {name} - price {price} > {max_price} (rule: {keyword})")
                return False, 0
            return True, qty

    return False, 0


def check_tantis_trigger(event_type: str, product: dict):
    """
    Check if tantis auto-buy should be triggered.
    Adds matching products to batch (launched later by flush_tantis_batch).

    Args:
        event_type: "NEW_PRODUCT", "RESTOCK", or "PRICE_CHANGE"
        product: dict with keys: id, name, price, shop, url, image, stock, available
    """
    global _batch

    if event_type not in ("NEW_PRODUCT", "RESTOCK", "PRICE_CHANGE"):
        return

    triggered, qty = should_trigger(product)
    if not triggered:
        return

    product_id = extract_product_id(product.get("id", ""))
    if not product_id:
        log.warning(f"[tantis_trigger] Could not extract ID from: {product.get('id')}")
        return

    name = product.get("name", "?")
    price = product.get("price", "?")

    # Check if already completed
    if is_tantis_completed(product_id):
        log.info(f"[tantis_trigger] Already bought on all accounts: {name}, skip")
        return

    # Check if already in batch (avoid duplicates from multiple events)
    if any(pid == product_id for pid, _, _ in _batch):
        log.info(f"[tantis_trigger] Already in batch: {name} (ID {product_id})")
        return

    log.info(f"[tantis_trigger] BATCH ADD: {event_type}: {name} ({price}) -> ID {product_id} (qty={qty})")
    _batch.append((product_id, name, qty))


def flush_tantis_batch():
    """
    Launch bot with all collected products (if any).
    Call this AFTER all events for tantis shop are processed in detect_and_send().
    """
    global _batch
    if not _batch:
        return

    product_ids = [pid for pid, _, _ in _batch]
    names = [name for _, name, _ in _batch]
    # Use minimum qty from batch (if mixed FP3 + 30th, use 1 to be safe)
    min_qty = min(q for _, _, q in _batch)

    log.info(f"[tantis_trigger] FLUSH BATCH: {len(_batch)} products -> {product_ids}")
    log.info(f"[tantis_trigger] Products: {names}")

    # Clear batch
    batch_copy = list(_batch)
    _batch = []

    # Launch bot with ALL product IDs
    try:
        cmd = [PYTHON, BOT_PATH, "--all", "--qty", str(min_qty)] + product_ids
        log.info(f"[tantis_trigger] Running: {' '.join(cmd)}")

        stdout_log = os.path.join(BASE_DIR, "tantis_autobuy_stdout.log")
        stderr_log = os.path.join(BASE_DIR, "tantis_autobuy_stderr.log")

        env = os.environ.copy()
        env["DISPLAY"] = ":99"

        with open(stdout_log, "a") as out, open(stderr_log, "a") as err:
            subprocess.Popen(
                cmd,
                stdout=out,
                stderr=err,
                cwd=BASE_DIR,
                start_new_session=True,
                env=env,
            )
        log.info(f"[tantis_trigger] Bot launched for {len(batch_copy)} products: {product_ids}")
    except Exception as e:
        log.error(f"[tantis_trigger] Failed to launch bot: {e}")
