"""
HYDRA v3 Engine Runner
======================
Runs API-first engines ALONGSIDE existing shops/*.py scrapers.
Both run simultaneously - whichever detects faster, triggers the bot.

Architecture:
- Each engine is an independent async loop with its own poll interval
- Engines report to the SAME detector.py → same triggers fire
- Uses same database for state tracking (detect_and_send compares old vs new)
- If engine fails, old scraper still runs (zero risk)
- Dedup: since engine and old scraper share DB state, only the FIRST to
  detect a change will fire triggers (second sees no change in old_products)

Usage:
  From main.py, add engine processes to the multiprocessing pool.
  Or run standalone: python -m engines.engine_runner
"""

import asyncio
import importlib
import logging
import os
import sys
import random
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Add parent directory to path for imports
DIR = Path(__file__).parent.parent
sys.path.insert(0, str(DIR))

from config import LOG_PATH
from database import init_db, get_shop_products, save_products_batch, is_snapshot_done, mark_snapshot_done
from detector import detect_and_send
from sanitize import sanitize_batch

logger = logging.getLogger("monitor")

# ============================================================
# ENGINE REGISTRY
# ============================================================

# Each entry: (module_path, shop_name, poll_interval_seconds)
ENGINES = [
    # ("engines.tcgumisia_api", "tcgumisia", 3),  # DISABLED — causes 429 spam (same IP as scraper)
    ("engines.tcgumisia_proxy_poller", "tcgumisia", 20),  # Pre-order via mobile proxy, 20s interval (was 10 — rate limited)
    # ("engines.strefatcg_api", "strefatcg", 3),  # DISABLED — old BS4 scraper only
    # Add more engines here as they're built:
    # ("engines.kartexpol_api", "kartexpol", 5),
]


# ============================================================
# ENGINE WORKER
# ============================================================

async def engine_worker(module_name: str, shop_name: str, poll_interval: int):
    """
    Independent async worker for one engine.
    Same pattern as main.py shop_worker but with custom interval.
    """
    # Initial stagger to avoid thundering herd
    await asyncio.sleep(random.uniform(0, 5))

    try:
        module = importlib.import_module(module_name)
    except Exception as e:
        logger.error(f"[ENGINE:{shop_name}] Failed to import {module_name}: {e}")
        return

    if not hasattr(module, "get_products"):
        logger.error(f"[ENGINE:{shop_name}] Module has no get_products()")
        return

    logger.info(f"[ENGINE:{shop_name}] Starting (poll every {poll_interval}s)")

    stats = {"ok": 0, "err": 0, "consecutive_err": 0}

    while True:
        try:
            start = datetime.now()

            # Scrape via engine
            get_fn = module.get_products
            if asyncio.iscoroutinefunction(get_fn):
                products = await asyncio.wait_for(get_fn(), timeout=60)
            else:
                loop = asyncio.get_running_loop()
                products = await asyncio.wait_for(
                    loop.run_in_executor(None, get_fn), timeout=60
                )

            if not products:
                stats["consecutive_err"] += 1
                if stats["consecutive_err"] >= 10:
                    logger.warning(f"[ENGINE:{shop_name}] 10 consecutive failures, backing off 30s")
                    await asyncio.sleep(30)
                    stats["consecutive_err"] = 0
                else:
                    await asyncio.sleep(poll_interval * 2)
                continue

            products = sanitize_batch(products)
            if not products:
                stats["consecutive_err"] += 1
                await asyncio.sleep(poll_interval)
                continue

            # Detect changes (same as main.py)
            shop_field = products[0].get("shop", shop_name)
            old = await get_shop_products(shop_field)

            snapshot = await is_snapshot_done(f"engine_{shop_name}")
            was_first = await detect_and_send(shop_name, old, products, snapshot)

            if was_first or not snapshot:
                await mark_snapshot_done(f"engine_{shop_name}")

            # Save to same DB (shared state with old scraper)
            await save_products_batch(products)

            scan_time = (datetime.now() - start).total_seconds()
            stats["ok"] += 1
            stats["consecutive_err"] = 0

            if stats["ok"] % 20 == 0:  # Log every 20th successful poll
                logger.info(
                    f"[{shop_name}] {len(products)} produktow w {scan_time:.1f}s"
                )

        except asyncio.TimeoutError:
            logger.warning(f"[{shop_name}] Timeout")
            stats["consecutive_err"] += 1
        except asyncio.CancelledError:
            logger.info(f"[ENGINE:{shop_name}] Cancelled, shutting down")
            return
        except Exception as e:
            logger.error(f"[{shop_name}] ERROR: {e}")
            stats["consecutive_err"] += 1

        # Wait before next poll
        # Add small jitter to prevent all engines polling at the exact same time
        jitter = random.uniform(0, 1)
        await asyncio.sleep(poll_interval + jitter)


# ============================================================
# ENGINE PROCESS (for multiprocessing from main.py)
# ============================================================

def run_engines_process():
    """
    Entry point for a dedicated engine process.
    Runs all registered engines as async tasks in one event loop.
    """
    # Setup logging
    log = logging.getLogger("monitor")
    log.setLevel(logging.INFO)
    log.handlers.clear()

    fh = RotatingFileHandler(LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3)
    fh.setFormatter(logging.Formatter("%(asctime)s [ENGINE] [%(levelname)s] %(message)s"))
    log.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s [ENGINE] [%(levelname)s] %(message)s"))
    log.addHandler(ch)

    log.info(f"[ENGINE] Process starting with {len(ENGINES)} engines")

    if not ENGINES:
        log.info("[ENGINE] No engines registered — sleeping (idle)")
        import time
        while True:
            time.sleep(3600)

    async def _run_all():
        await init_db()
        tasks = [
            asyncio.create_task(engine_worker(mod, name, interval))
            for mod, name, interval in ENGINES
        ]
        log.info(f"[ENGINE] All {len(tasks)} engine workers started")
        await asyncio.gather(*tasks)

    asyncio.run(_run_all())


# ============================================================
# STANDALONE MODE
# ============================================================

if __name__ == "__main__":
    run_engines_process()
