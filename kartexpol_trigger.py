import subprocess
import logging
log = logging.getLogger("monitor")

def check_kartexpol_autobuy(shop, event_type, product, batch):
    if shop != "kartexpol":
        return
    if event_type not in ("NEW_PRODUCT", "RESTOCK", "PRICE_CHANGE"):
        return
    name = product.get("name", "").lower()
    if "30" in name:
        batch.append(product)
        log.info(f"[KARTEXPOL_BUY] Queued: {product.get('name')}")

def fire_kartexpol_buy(products):
    urls = [p.get("url","") for p in products if p.get("url")]
    if not urls:
        return
    log.info(f"[KARTEXPOL_BUY] Firing bot for {len(urls)} products")
    cmd = ["/opt/pokemon-monitor-v2/venv/bin/python3","/opt/pokemon-monitor-v2/kartexpol_autobuy.py"] + urls
    subprocess.Popen(cmd, stdout=open("/opt/pokemon-monitor-v2/kartexpol_autobuy_stdout.log","a"), stderr=open("/opt/pokemon-monitor-v2/kartexpol_autobuy_stderr.log","a"), start_new_session=True)
