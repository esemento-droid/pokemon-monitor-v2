import subprocess, logging, re

log = logging.getLogger("monitor")
TRIGGER_KW = re.compile(r"first.partner|illustration.collection|30th|30.anniversary|30.lecie|30.rocznica", re.IGNORECASE)
PYTHON = "/opt/pokemon-monitor-v2/venv/bin/python3"
SCRIPT = "/opt/pokemon-monitor-v2/smyk_autobuy.py"


def check_smyk_autobuy(shop, event_type, product):
    if shop != "smyk.com":
        return
    if event_type not in ("NEW_PRODUCT", "RESTOCK", "PRICE_CHANGE"):
        return
    if not product.get("available"):
        return
    if not TRIGGER_KW.search(product.get("name", "")):
        return
    # Price filter (FP3/illustration <= 160, 30th = no limit)
    price = product.get("price", 0)
    if isinstance(price, str):
        import re as _re
        m = _re.search(r'(\d+[,.]?\d*)', price.replace(" ", ""))
        price = float(m.group(1).replace(",", ".")) if m else 0
    name_lower = product.get("name", "").lower()
    is_30th = any(kw in name_lower for kw in ["30th", "30 anniversary", "30 lecie", "30 rocznica", "30-lecie"])
    if not is_30th:
        if price > 160 or price <= 0:
            log.info(f"[SMYK-TRIGGER] Price {price} > 160 or 0, skip: {product.get('name','')}")
            return
    else:
        # 30th products — apply per-product price limits
        if price <= 0:
            log.info(f"[SMYK-TRIGGER] 30th price {price} = 0, skip: {product.get('name','')}")
            return
        SMYK_30TH_LIMITS = {
            "elite trainer box": 401,
            "tin": 145,
            "sticker": 120,
            "booster bundle": 249,
            "ex box": 162,
            "poster": 121,
            "2-pack": 81,
            "binder": 251,
        }
        max_price = 500  # default for unknown 30th
        for keyword, limit in SMYK_30TH_LIMITS.items():
            if keyword in name_lower:
                max_price = limit
                break
        if price >= max_price:
            log.info(f"[SMYK-TRIGGER] 30th price {price} >= {max_price}, skip: {product.get('name','')}")
            return
    url = product.get("url", "")
    if is_smyk_completed(url):
        log.info(f"[SMYK-TRIGGER] Already bought: {product['name']}, skip")
        return
    log.info(f"[SMYK-TRIGGER] MATCH! {event_type}: {product['name']} -> {url}")
    try:
        subprocess.Popen(
            [PYTHON, SCRIPT, url],
            stdout=open("/opt/pokemon-monitor-v2/smyk_autobuy_stdout.log", "a"),
            stderr=open("/opt/pokemon-monitor-v2/smyk_autobuy_stderr.log", "a"),
            start_new_session=True
        )
        log.info("[SMYK-TRIGGER] Auto-buy launched (4 accounts)!")
        try:
            import requests as _req
            from config import DISCORD_WEBHOOK
            if DISCORD_WEBHOOK:
                _req.post(DISCORD_WEBHOOK, json={"content": f"🛒 **SMYK BOT TRIGGERED!**\n{product.get('name','')}\n{product.get('price','')} zł\n{url}"}, timeout=5)
        except: pass
        mark_smyk_completed(url)
    except Exception as e:
        log.error(f"[SMYK-TRIGGER] Failed to launch: {e}")
