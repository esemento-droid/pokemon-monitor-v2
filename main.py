#!/usr/bin/env python3
"""
Pokemon Monitor v2 — BLITZ Engine (Optimized)

Architektura:
- 1 proces Python, 1 event loop asyncio
- Kazdy sklep = osobny asyncio.Task (niezalezny worker)
- ZERO lockow, ZERO kolejek, ZERO czekania na inne sklepy
- Shared DB pool (asyncpg) + shared Discord sender (fire-and-forget)
- Per-shop timeout: 60s (HTTP), 300s (nodriver/Chrome)
- Per-shop delay: adaptive na podstawie kategorii + czasu skanu
- Graceful error handling: backoff po errorach, alarm po 5 z rzedu

Docelowo: skaluje sie do 300+ sklepow na 8GB RAM (vs orchestrator max ~130)
"""

import asyncio
import os
import sys
import importlib
import random
import logging
import signal
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Ensure project root on path
DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

from config import CHECK_MIN, CHECK_MAX, LOG_PATH, DISCORD_WEBHOOK
from database import init_db, get_shop_products, save_products_batch, is_snapshot_done, mark_snapshot_done
from detector import detect_and_send
from discord_sender import discord
from sanitize import sanitize_batch

# ============================================================
# LOGGING
# ============================================================
logger = logging.getLogger("monitor")
logger.setLevel(logging.INFO)
fh = RotatingFileHandler(LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3)
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(fh)
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(ch)

# ============================================================
# SHOP CATEGORIES — delay i timeout per typ sklepu
# Identyczne z orchestrator.py — zachowuje pelna kompatybilnosc
# ============================================================

# Nodriver/Chrome shops — dlugi timeout (300s), dlugi delay (90-180s)
NODRIVER_SHOPS = {
    "empik", "proshop", "boosterpoint",
    "dragonus", "piwniczaki", "rgfk", "strefamarzen", "wilczek", "tantis",
}

# Shopify shops — rate limited, delay 180-300s
SHOPIFY_SHOPS = {"pokeloot", "skladgier"}

# Slow shops — wolne serwery/paginacja, delay 45-90s
SLOW_SHOPS = {
    "am76", "blindbox", "flamberg", "mrpuggy", "pikashop",
    "paladynat", "czytam", "swiatkart",
}

# Bardzo wolne (>120s avg scan) — adaptive delay
VERY_SLOW_SHOPS = {
    "efantasy", "twojekarty", "canislupus", "tcgtrener",
    "mangiusmoczejciotki", "vanaheim", "kartomaniak",
}

# Reszta: fast shops — delay 5-15s (CHECK_MIN - CHECK_MAX)

# ============================================================
# TIMEOUT per kategoria
# ============================================================
TIMEOUT_NODRIVER = 300   # Chrome shops need time to start + CF bypass
TIMEOUT_SLOW = 180       # Slow paginacja
TIMEOUT_DEFAULT = 60     # Standard HTTP scrapers

# ============================================================
# STATS
# ============================================================
scan_stats = {}
_shutdown = False


# ============================================================
# LOAD SHOPS
# ============================================================
def load_shops():
    """Import all shop modules from shops/ directory."""
    shops = []
    shops_dir = os.path.join(DIR, "shops")
    for filename in sorted(os.listdir(shops_dir)):
        if not filename.endswith(".py"):
            continue
        if filename.startswith("__") or filename in ("base.py", "template.py"):
            continue
        name = filename[:-3]
        try:
            module = importlib.import_module(f"shops.{name}")
            if hasattr(module, "get_products"):
                shops.append((name, module))
        except Exception as e:
            logger.error(f"[LOAD] X {name}: {e}")
    logger.info(f"[LOAD] Aktywne sklepy: {len(shops)}")
    return shops


# ============================================================
# SHOP WORKER — jeden niezalezny task per sklep
# ============================================================
async def shop_worker(name, module):
    """
    Niezalezny worker dla jednego sklepu.
    Kazdy dziala w petli: scrape → detect → save → sleep.
    NIE czeka na inne sklepy. NIE uzywa lockow.
    """
    # Stagger start — nie odpala 130 sklepow na raz
    await asyncio.sleep(random.uniform(0, 30))

    scan_stats[name] = {"ok": 0, "err": 0, "last": None, "last_scan_time": 0}

    while not _shutdown:
        scan_time = 0.0
        try:
            start = datetime.now()
            products = None

            # --- SCRAPE ---
            timeout = _get_timeout(name)
            try:
                get_fn = module.get_products
                if asyncio.iscoroutinefunction(get_fn):
                    products = await asyncio.wait_for(get_fn(), timeout=timeout)
                else:
                    loop = asyncio.get_running_loop()
                    products = await asyncio.wait_for(
                        loop.run_in_executor(None, get_fn),
                        timeout=timeout
                    )
            except asyncio.TimeoutError:
                logger.warning(f"[{name}] Timeout {timeout}s")
                scan_stats[name]["err"] += 1
                await asyncio.sleep(_get_delay(name, error=True))
                continue
            except asyncio.CancelledError:
                return
            except Exception as e:
                raise  # Let outer handler catch

            # --- VALIDATE ---
            if not products:
                scan_stats[name]["err"] += 1
                await asyncio.sleep(_get_delay(name, error=True))
                continue

            products = sanitize_batch(products)
            if not products:
                scan_stats[name]["err"] += 1
                await asyncio.sleep(_get_delay(name, error=True))
                continue

            # --- DETECT CHANGES ---
            shop_field = products[0].get("shop", name)
            old = await get_shop_products(shop_field)

            # Ochrona: jesli scraper zwrocil 0 ale DB ma dane — pomijamy
            # (już po sanitize, wiec products nie jest puste tutaj)

            snapshot = await is_snapshot_done(name)
            was_first = await detect_and_send(name, old, products, snapshot)

            if was_first or not snapshot:
                await mark_snapshot_done(name)

            # --- SAVE ---
            await save_products_batch(products)

            # --- STATS ---
            scan_time = (datetime.now() - start).total_seconds()
            scan_stats[name]["ok"] += 1
            scan_stats[name]["err"] = 0
            scan_stats[name]["last"] = datetime.now().isoformat()
            scan_stats[name]["last_scan_time"] = scan_time

            logger.info(f"[{name}] {len(products)} produktow w {scan_time:.1f}s")

        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"[{name}] ERROR: {e}")
            scan_stats[name]["err"] += 1

            # Alarm po 5 errorach z rzedu
            if scan_stats[name]["err"] == 5:
                await _send_alarm(name, e)

        # --- DELAY ---
        delay = _get_delay(name, error=(scan_stats[name]["err"] > 0), scan_time=scan_time)
        await asyncio.sleep(delay)


# ============================================================
# DELAY LOGIC — per-category + adaptive
# ============================================================
def _get_delay(name, error=False, scan_time=0.0):
    """
    Oblicz delay miedzy skanami.
    - Per-category base delay (jak orchestrator)
    - Adaptive: jesli skan trwal dluzej niz delay, czekaj przynajmniej 1x scan_time
    - Error backoff: 60-120s po bledach, eskalacja po wiekszej liczbie
    """
    errs = scan_stats.get(name, {}).get("err", 0)

    # Error backoff
    if error or errs >= 5:
        return random.randint(60, 120)
    elif errs >= 3:
        return random.randint(30, 60)

    # Category-based delay
    if name in NODRIVER_SHOPS:
        base_delay = random.randint(90, 180)
    elif name in SHOPIFY_SHOPS:
        base_delay = random.randint(180, 300)
    elif name in VERY_SLOW_SHOPS:
        base_delay = random.randint(60, 120)
    elif name in SLOW_SHOPS:
        base_delay = random.randint(45, 90)
    else:
        base_delay = random.randint(CHECK_MIN, CHECK_MAX)

    # Adaptive: nie skanuj szybciej niz trwal ostatni skan
    if scan_time > base_delay:
        return int(scan_time * 1.2)

    return base_delay


def _get_timeout(name):
    """Timeout per shop category."""
    if name in NODRIVER_SHOPS:
        return TIMEOUT_NODRIVER
    elif name in VERY_SLOW_SHOPS or name in SLOW_SHOPS:
        return TIMEOUT_SLOW
    return TIMEOUT_DEFAULT


# ============================================================
# HEARTBEAT — status co 6h
# ============================================================
async def heartbeat_worker():
    """Heartbeat co 6 godzin — ile sklepow OK, ile errorow."""
    await asyncio.sleep(120)  # Daj systemowi 2min na rozgrzanie
    while not _shutdown:
        try:
            import aiohttp
            shops_ok = sum(1 for s in scan_stats.values() if s["ok"] > 0)
            total_scans = sum(s["ok"] + s["err"] for s in scan_stats.values())
            errors_active = sum(1 for s in scan_stats.values() if s["err"] >= 3)
            top_errors = sorted(
                [(k, v["err"]) for k, v in scan_stats.items() if v["err"] >= 3],
                key=lambda x: -x[1]
            )[:5]
            err_list = ", ".join(f"{k}({v})" for k, v in top_errors) if top_errors else "brak"

            msg = (
                f"\u2764\ufe0f **Heartbeat** | "
                f"{shops_ok} sklepow OK | "
                f"{total_scans} skanow | "
                f"{errors_active} z problemami\n"
                f"Errors: {err_list}"
            )
            async with aiohttp.ClientSession() as session:
                await session.post(DISCORD_WEBHOOK, json={"content": msg})
        except Exception:
            pass
        await asyncio.sleep(21600)  # 6h


# ============================================================
# ALARM — po 5 errorach z rzedu
# ============================================================
async def _send_alarm(name, error):
    """Wyslij alarm na Discord po 5 errorach z rzedu."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(DISCORD_WEBHOOK, json={
                "content": f"\u26a0\ufe0f ALARM [{name}] 5 errorow z rzedu: {error}"
            })
    except Exception:
        pass


# ============================================================
# MAIN — entry point
# ============================================================
async def main():
    global _shutdown

    logger.info("=" * 60)
    logger.info("Pokemon Monitor v2 — BLITZ Engine (Optimized)")
    logger.info("=" * 60)

    # Init shared resources (ONCE)
    await init_db()
    discord.start()

    # Load all shops
    shops = load_shops()
    if not shops:
        logger.error("Brak sklepow!")
        return

    # Categorize shops for logging
    nodriver_count = sum(1 for n, _ in shops if n in NODRIVER_SHOPS)
    slow_count = sum(1 for n, _ in shops if n in SLOW_SHOPS or n in VERY_SLOW_SHOPS)
    fast_count = len(shops) - nodriver_count - slow_count

    logger.info(f"Sklepy: {len(shops)} total ({fast_count} fast, {slow_count} slow, {nodriver_count} nodriver)")
    logger.info(f"Architektura: 1 proces, {len(shops)} niezaleznych async tasks")
    logger.info(f"Zero lockow, zero kolejek — kazdy sklep osobno")
    logger.info(f"Timeouts: default={TIMEOUT_DEFAULT}s, slow={TIMEOUT_SLOW}s, nodriver={TIMEOUT_NODRIVER}s")
    logger.info(f"Discord: fire-and-forget queue (max 500, {25}/min)")

    # Create independent worker per shop
    tasks = []
    for name, module in shops:
        tasks.append(asyncio.create_task(shop_worker(name, module), name=f"shop_{name}"))
    tasks.append(asyncio.create_task(heartbeat_worker(), name="heartbeat"))

    logger.info(f"Uruchomiono {len(shops)} workerow + heartbeat")

    # Graceful shutdown on SIGTERM/SIGINT
    def signal_handler():
        global _shutdown
        _shutdown = True
        logger.info("Otrzymano SIGTERM/SIGINT — zamykanie...")

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    # Run until shutdown
    try:
        # Wait for all tasks (they run forever until _shutdown)
        await asyncio.gather(*tasks, return_exceptions=True)
    except KeyboardInterrupt:
        _shutdown = True
    finally:
        logger.info("Zamykanie Discord sender...")
        await discord.close()
        logger.info("Pokemon Monitor v2 — STOP")


if __name__ == "__main__":
    asyncio.run(main())
