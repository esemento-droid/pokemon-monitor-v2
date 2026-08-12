"""
Universal Trigger — one engine, config-driven.
Replaces 9 separate trigger files with one JSON config.

Usage in detector.py:
    from universal_trigger import check_trigger, flush_all_batches
    check_trigger(shop_name, event_type, product)
    flush_all_batches()
"""

import asyncio
import json
import logging
import os
import random
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger("universal_trigger")

BASE_DIR = Path("/opt/pokemon-monitor-v2")
CONFIG_PATH = BASE_DIR / "trigger_config.json"

# === GLOBAL STATE ===
_config: Dict = {}
_batches: Dict[str, List] = {}  # trigger_name -> [products]
_config_loaded_at: float = 0
CONFIG_RELOAD_INTERVAL = 60  # reload config every 60s (allows hot-reload)


def _load_config():
    """Load trigger config from JSON. Hot-reloadable."""
    global _config, _config_loaded_at
    import time
    if _config and (time.time() - _config_loaded_at) < CONFIG_RELOAD_INTERVAL:
        return _config
    try:
        raw = CONFIG_PATH.read_text()
        _config = json.loads(raw)
        # Remove comment keys
        _config.pop("_comment", None)
        _config_loaded_at = time.time()
        log.info(f"[TRIGGER] Config loaded: {len(_config)} triggers")
    except Exception as e:
        log.error(f"[TRIGGER] Config load error: {e}")
        if not _config:
            _config = {}
    return _config


def _load_completed(completed_file: str) -> Dict:
    """Load completed orders JSON."""
    path = BASE_DIR / completed_file
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def _is_all_completed(completed_file: str, product_id: str, accounts: List[str]) -> bool:
    """Check if all accounts already bought this product."""
    completed = _load_completed(completed_file)
    bought = completed.get(product_id, [])
    return all(acc in bought for acc in accounts)


def _matches_rules(name: str, price_str: str, rules: List[Dict], exclude: List[str]) -> Optional[Dict]:
    """
    Check if product matches any rule. Returns matching rule or None.
    """
    name_lower = name.lower()

    # Check excludes first
    for excl in exclude:
        if excl.lower() in name_lower:
            return None

    # Parse price
    try:
        price_clean = price_str.replace("PLN", "").replace("zł", "").replace("zl", "").replace(",", ".").replace(" ", "").strip()
        price = float(price_clean)
    except (ValueError, TypeError):
        price = 9999

    # Check each rule
    for rule in rules:
        pattern = rule.get("match", "")
        max_price = rule.get("max_price", 9999)

        # Pattern match (supports | for OR)
        if pattern:
            keywords = pattern.split("|")
            if not any(kw.strip().lower() in name_lower for kw in keywords):
                continue

        # Price check
        if price > max_price:
            continue

        # Match found!
        return rule

    return None


def _get_product_id(product: Dict) -> str:
    """Extract product ID from URL or product dict."""
    url = product.get("url", "")
    if url:
        slug = url.rstrip('/').split('/')[-1]
        slug = re.sub(r'/\d+$', '', slug)
        return slug
    return str(product.get("id", ""))


def check_trigger(shop_name: str, event_type: str, product: Dict):
    """
    Check if product should trigger any bot. Called from detector.py.
    Adds matching products to batch (or fires immediately for non-batch triggers).
    """
    global _batches
    config = _load_config()

    if not product.get("available", False):
        return

    name = product.get("name", "")
    price_str = product.get("price", "9999")
    url = product.get("url", "")
    product_shop = product.get("shop", shop_name)

    for trigger_name, trigger_cfg in config.items():
        # Match shop
        shop_match = trigger_cfg.get("shop_match", "")
        if shop_match and shop_match not in product_shop.lower() and shop_match not in shop_name.lower():
            continue

        # Match event type
        allowed_events = trigger_cfg.get("events", ["NEW_PRODUCT", "RESTOCK"])
        if event_type not in allowed_events:
            continue

        # Match rules
        rules = trigger_cfg.get("rules", [])
        exclude = trigger_cfg.get("exclude", [])
        matched_rule = _matches_rules(name, price_str, rules, exclude)
        if not matched_rule:
            continue

        # Check if already completed
        completed_file = trigger_cfg.get("completed_file", "")
        accounts = trigger_cfg.get("accounts", [])
        product_id = _get_product_id(product)

        if completed_file and _is_all_completed(completed_file, product_id, accounts):
            continue

        # Determine qty
        qty_min = matched_rule.get("qty_min", 1)
        qty_max = matched_rule.get("qty_max", 1)
        qty = random.randint(qty_min, qty_max)

        log.info(f"[TRIGGER:{trigger_name}] MATCH! event={event_type} name='{name}' qty={qty} price={price_str}")

        # Add to batch
        if trigger_name not in _batches:
            _batches[trigger_name] = []

        # Dedup within batch
        if not any(p["url"] == url for p in _batches[trigger_name]):
            _batches[trigger_name].append({
                "url": url,
                "name": name,
                "id": product_id,
                "price": price_str,
                "qty": qty,
                "rule": matched_rule.get("match", ""),
            })


def flush_all_batches():
    """
    Called after detect_and_send finishes. Launch bots for all collected batches.
    """
    global _batches
    config = _load_config()

    for trigger_name, products in _batches.items():
        if not products:
            continue

        trigger_cfg = config.get(trigger_name, {})
        if not trigger_cfg:
            continue

        _launch_bot(trigger_name, trigger_cfg, products)

    _batches = {}


def _launch_bot(trigger_name: str, trigger_cfg: Dict, products: List[Dict]):
    """Launch bot process for this trigger."""
    bot_file = trigger_cfg.get("bot", "")
    bot_path = BASE_DIR / bot_file
    if not bot_path.exists():
        log.error(f"[TRIGGER:{trigger_name}] Bot not found: {bot_path}")
        return

    # Discord notify
    webhook_file = trigger_cfg.get("webhook_file", "")
    if webhook_file:
        _notify_discord(trigger_name, products, webhook_file)

    # Build command
    accounts = trigger_cfg.get("accounts", [])
    bot_args = trigger_cfg.get("bot_args", [])
    batch_mode = trigger_cfg.get("batch_mode", True)

    cmd = [
        str(BASE_DIR / "venv" / "bin" / "python3"), "-u",
        str(bot_path),
    ]

    if batch_mode:
        products_json = json.dumps([{"url": p["url"], "qty": p["qty"]} for p in products])
        cmd.extend(["--products-json", products_json])
    else:
        # Single product mode — pass first product URL
        if products:
            cmd.extend(["--url", products[0]["url"]])
            if products[0].get("qty", 1) > 1:
                cmd.extend(["--qty", str(products[0]["qty"])])

    cmd.extend(bot_args)

    env = {**os.environ, "DISPLAY": ":99"}

    log.info(f"[TRIGGER:{trigger_name}] Launching bot: {len(products)} products, cmd={bot_file}")
    try:
        subprocess.Popen(
            cmd,
            env=env,
            stdout=open(str(BASE_DIR / f"{trigger_name}_trigger_stdout.log"), "a"),
            stderr=open(str(BASE_DIR / f"{trigger_name}_trigger_stderr.log"), "a"),
            cwd=str(BASE_DIR)
        )
        log.info(f"[TRIGGER:{trigger_name}] Bot launched!")

        # Log to DB (async — fire and forget)
        try:
            from database import log_event
            import asyncio
            for p in products:
                asyncio.ensure_future(log_event(
                    trigger_name, "BOT_TRIGGER", p["id"], p["name"], p["price"], p["url"],
                    {"qty": p["qty"], "accounts": len(accounts), "rule": p.get("rule", "")}
                ))
        except Exception:
            pass

    except Exception as e:
        log.error(f"[TRIGGER:{trigger_name}] Failed to launch bot: {e}")


def _notify_discord(trigger_name: str, products: List[Dict], webhook_file: str):
    """Send trigger notification to Discord."""
    try:
        wh_path = BASE_DIR / webhook_file
        if not wh_path.exists():
            return
        wh_url = wh_path.read_text().strip()
        if not wh_url:
            return

        product_lines = "\n".join([f"• {p['name'][:50]} (qty:{p['qty']}, {p['price']})" for p in products[:10]])
        msg = f"🚨 **{trigger_name.upper()} TRIGGER** — {len(products)} produktów!\n{product_lines}\nOdpalam bota..."

        import aiohttp
        async def _send():
            async with aiohttp.ClientSession() as s:
                await s.post(wh_url, json={"content": msg}, timeout=aiohttp.ClientTimeout(total=10))

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_send())
            else:
                asyncio.run(_send())
        except Exception:
            pass
    except Exception as e:
        log.warning(f"[TRIGGER:{trigger_name}] Discord notify failed: {e}")
