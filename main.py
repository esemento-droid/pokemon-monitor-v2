#!/usr/bin/env python3
"""
Pokemon Monitor v2 — MULTI-PROCESS Engine

Architektura: 3 niezalezne procesy (fork) + nodriver subprocess
- FAST process: ~100 HTTP shops (scan 1-15s, delay 5-15s)
- SLOW process: ~20+ shops (scan 30-120s, delay 45-120s)
- NODRIVER: subprocess via runner.py per Chrome shop (9 shops)

Kazdy proces ma SWOJ event loop — nie przeszkadzaja sobie.
Zero lockow, zero kolejek, zero czekania.
Skaluje do 300+ shops (dodaj kolejny FAST process).
"""

import asyncio
import os
import sys
import importlib
import random
import logging
import signal
import multiprocessing
from logging.handlers import RotatingFileHandler
from datetime import datetime

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

from config import CHECK_MIN, CHECK_MAX, LOG_PATH, DISCORD_WEBHOOK
from database import init_db, get_shop_products, save_products_batch, is_snapshot_done, mark_snapshot_done, should_turbo_mode
from detector import detect_and_send
from discord_sender import discord
from sanitize import sanitize_batch
from engines.engine_runner import run_engines_process

# ============================================================
# SHOP CATEGORIES
# ============================================================

NODRIVER_SHOPS = {
    "empik", "mediaexpert", "proshop", "boosterpoint",
    "strefamarzen", "tantis",
    "libristo",
}

SHOPIFY_SHOPS = {"pokeloot", "skladgier"}

SLOW_SHOPS = {
    "am76", "blindbox", "flamberg", "mrpuggy", "pikashop",
    "paladynat", "czytam", "kuzniakart", "sklepkleks",
    "battlestash", "tcg-zielona", "morigal",
    "eduksiazka", "dystryktzero", "gralnia", "xjoy", "mepel",
    "maginarium", "monsteriada", "wilczek",
}

VERY_SLOW_SHOPS = {
    "efantasy", "twojekarty", "canislupus", "tcgtrener",
    "mangiusmoczejciotki", "vanaheim", "kartomaniak", "limango",
    "bonito",
}

# All non-fast shops (go to SLOW process)
ALL_SLOW = SLOW_SHOPS | VERY_SLOW_SHOPS | SHOPIFY_SHOPS

TIMEOUT_NODRIVER = 120
TIMEOUT_SLOW = 120
TIMEOUT_DEFAULT = 60

# ============================================================
# LOGGING (per-process)
# ============================================================

def setup_logger(process_name):
    logger = logging.getLogger("monitor")
    logger.setLevel(logging.INFO)
    # Clear existing handlers (important after fork)
    logger.handlers.clear()
    fh = RotatingFileHandler(LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3)
    fh.setFormatter(logging.Formatter(f"%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter(f"%(asctime)s [{process_name}] [%(levelname)s] %(message)s"))
    logger.addHandler(ch)
    return logger


# ============================================================
# LOAD SHOPS
# ============================================================

def load_shops():
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
            if getattr(module, "SHOP_DISABLED", False):
                logging.getLogger("monitor").info(f"[LOAD] SKIP {name} (SHOP_DISABLED)")
                continue
            if hasattr(module, "get_products"):
                shops.append((name, module))
        except Exception as e:
            logging.getLogger("monitor").error(f"[LOAD] X {name}: {e}")
    return shops


# ============================================================
# SHOP WORKER (async, in-process)
# ============================================================

async def shop_worker(name, module, logger, process_type):
    """Independent async worker for one shop."""
    # Staggered startup: SLOW shops spread over 120s (prevents FS thundering herd)
    # FAST shops spread over 30s (lightweight HTTP, no issue)
    if name in SLOW_SHOPS or name in VERY_SLOW_SHOPS:
        await asyncio.sleep(random.uniform(5, 120))
    else:
        await asyncio.sleep(random.uniform(0, 30))

    stats = {"ok": 0, "err": 0, "consecutive_err": 0, "turbo": False, "cooldown_until": 0}
    _shutdown = False

    while not _shutdown:
        scan_time = 0.0

        # === ERROR RECOVERY: Cooldown check ===
        import time as _time
        if stats.get("cooldown_until", 0) > _time.time():
            remaining = int(stats["cooldown_until"] - _time.time())
            if remaining % 300 == 0:  # Log every 5 min during cooldown
                logger.info(f"[{name}] Cooldown: {remaining}s remaining")
            await asyncio.sleep(30)
            continue

        try:
            start = datetime.now()

            # Timeout based on category (adaptive: increase after timeouts)
            if name in VERY_SLOW_SHOPS:
                timeout = TIMEOUT_NODRIVER
            elif name in SLOW_SHOPS:
                timeout = TIMEOUT_SLOW
            else:
                timeout = TIMEOUT_DEFAULT

            # Adaptive timeout: if last scan was timeout, increase by 50%
            if stats.get("last_timeout", False):
                timeout = int(timeout * 1.5)
                stats["last_timeout"] = False

            # Scrape (with 1 retry on connection error)
            products = None
            for attempt in range(2):
                try:
                    get_fn = module.get_products
                    if asyncio.iscoroutinefunction(get_fn):
                        products = await asyncio.wait_for(get_fn(), timeout=timeout)
                    else:
                        loop = asyncio.get_running_loop()
                        products = await asyncio.wait_for(
                            loop.run_in_executor(None, get_fn), timeout=timeout
                        )
                    break  # Success
                except asyncio.TimeoutError:
                    logger.warning(f"[{name}] Timeout {timeout}s")
                    stats["last_timeout"] = True
                    break  # Don't retry timeouts
                except asyncio.CancelledError:
                    return
                except Exception as e:
                    if attempt == 0 and "Cannot connect" in str(e):
                        await asyncio.sleep(random.uniform(2, 5))
                        continue  # Retry once
                    raise

            if not products:
                stats["err"] += 1
                stats["consecutive_err"] = stats.get("consecutive_err", 0) + 1

                # === ERROR RECOVERY: Progressive cooldown ===
                consec = stats["consecutive_err"]
                if consec >= 20:
                    # 20+ errors: cooldown 30 min
                    stats["cooldown_until"] = _time.time() + 1800
                    logger.warning(f"[{name}] 20 consecutive errors! Cooldown 30min")
                elif consec >= 10:
                    # 10+ errors: cooldown 10 min
                    stats["cooldown_until"] = _time.time() + 600
                    logger.warning(f"[{name}] 10 consecutive errors! Cooldown 10min")

                await asyncio.sleep(_get_delay(name, stats, error=True))
                continue

            products = sanitize_batch(products)
            if not products:
                stats["err"] += 1
                stats["consecutive_err"] = stats.get("consecutive_err", 0) + 1
                await asyncio.sleep(_get_delay(name, stats, error=True))
                continue

            # Detect changes
            shop_field = products[0].get("shop", name)
            old = await get_shop_products(shop_field)

            snapshot = await is_snapshot_done(name)
            was_first = await detect_and_send(name, old, products, snapshot)

            if was_first or not snapshot:
                await mark_snapshot_done(name)

            await save_products_batch(products)

            scan_time = (datetime.now() - start).total_seconds()
            stats["ok"] += 1
            stats["err"] = 0
            stats["consecutive_err"] = 0  # Reset on success!
            logger.info(f"[{name}] {len(products)} produktow w {scan_time:.1f}s")

        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"[{name}] ERROR: {e}")
            stats["err"] += 1
            stats["consecutive_err"] = stats.get("consecutive_err", 0) + 1

            if stats["consecutive_err"] == 5:
                await _send_alarm(name, e, logger)

        # Delay with jitter
        # Check turbo mode (cross-shop intelligence)
        try:
            turbo = await should_turbo_mode(name)
            stats["turbo"] = turbo
        except Exception:
            stats["turbo"] = False

        delay = _get_delay(name, stats, error=(stats["err"] > 0), scan_time=scan_time)
        delay += random.uniform(0, 3)
        await asyncio.sleep(delay)


def _get_delay(name, stats, error=False, scan_time=0.0):
    errs = stats.get("err", 0)
    if error or errs >= 5:
        return random.randint(60, 120)
    elif errs >= 3:
        return random.randint(30, 60)

    # Check turbo mode (set by cross-shop intelligence)
    turbo = stats.get("turbo", False)
    if turbo:
        # TURBO: scan faster but safe (5-10s delay)
        return random.randint(5, 10)

    if name in VERY_SLOW_SHOPS:
        base = random.randint(45, 90)
    elif name in SLOW_SHOPS:
        base = random.randint(30, 60)
    elif name in SHOPIFY_SHOPS:
        base = random.randint(180, 300)
    else:
        base = random.randint(CHECK_MIN, CHECK_MAX)

    # If scan was fast, don't penalize with long delay
    # If scan was slow, give proportional rest (50% of scan time)
    if scan_time > 0:
        min_rest = max(10, int(scan_time * 0.3))
        if min_rest < base:
            return min_rest
    return base


async def _send_alarm(name, error, logger):
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(DISCORD_WEBHOOK, json={
                "content": f"\u26a0\ufe0f ALARM [{name}] 5 errorow z rzedu: {error}"
            })
    except:
        pass


# ============================================================
# PERSISTENT BROWSER SHOP WORKERS (new architecture)
# ============================================================
# All NODRIVER shops now use persistent browsers via browser_manager.py
# Old subprocess/pool code removed. See _async_nodriver() and _persistent_shop_worker().


# (Old pool_shop_worker and subprocess_shop_worker removed — replaced by _persistent_shop_worker)


# ============================================================
# HEARTBEAT
# ============================================================

async def heartbeat_worker(logger, process_name, shop_count):
    await asyncio.sleep(120)
    while True:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                await session.post(DISCORD_WEBHOOK, json={
                    "content": f"\u2764\ufe0f **{process_name}** | {shop_count} shops active"
                })
        except:
            pass
        await asyncio.sleep(21600)


# ============================================================
# PROCESS RUNNERS
# ============================================================

def run_fast_process(shop_names_modules):
    """Run FAST shops in own asyncio event loop."""
    asyncio.run(_async_process("FAST", shop_names_modules))


def run_slow_process(shop_names_modules):
    """Run SLOW shops in own asyncio event loop."""
    asyncio.run(_async_process("SLOW", shop_names_modules))


def run_nodriver_process(shop_names):
    """Run NODRIVER shops as subprocesses in own event loop."""
    asyncio.run(_async_nodriver("NODRIVER", shop_names))


async def _async_process(process_name, shop_names_modules):
    """Async entry for FAST/SLOW process."""
    logger = setup_logger(process_name)
    logger.info(f"=== {process_name} process starting ({len(shop_names_modules)} shops) ===")

    await init_db()
    discord.start()

    # SLOW process starts CF Bridge (replaces FlareSolverr Docker on :8191)
    if process_name == "SLOW":
        try:
            from cf_bridge import start_bridge
            await start_bridge()
            logger.info(f"[{process_name}] CF Bridge started on :8191 (FlareSolverr replacement)")
        except Exception as e:
            logger.warning(f"[{process_name}] CF Bridge failed to start: {e} — shops will use Docker FS as fallback")

    tasks = []
    for name, module in shop_names_modules:
        tasks.append(asyncio.create_task(shop_worker(name, module, logger, process_name)))
    tasks.append(asyncio.create_task(heartbeat_worker(logger, process_name, len(shop_names_modules))))

    logger.info(f"[{process_name}] {len(shop_names_modules)} async workers started")

    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except KeyboardInterrupt:
        pass
    finally:
        await discord.close()


async def _async_nodriver(process_name, shop_names):
    """
    Async entry for NODRIVER process — PERSISTENT BROWSER ARCHITECTURE.
    
    - 2 browsers (stealth patchright + standard playwright) — NEVER close
    - Each shop gets its OWN DEDICATED PAGE — lives forever
    - Scan = page.goto() + parse — zero startup, zero shutdown
    - Each shop runs independently (own asyncio task, own timer)
    - NO QUEUE. NO BLOCKING. Every shop scans in parallel.
    - Self-healing: page crash → recreate page, browser lives
    """
    logger = setup_logger(process_name)
    logger.info(f"=== {process_name} process starting ({len(shop_names)} shops) ===")
    logger.info(f"[{process_name}] Architecture: persistent browsers, dedicated pages, zero subprocess")

    await init_db()
    discord.start()

    from browser_manager import BrowserManager

    # Start persistent browsers
    mgr = BrowserManager()
    await mgr.start()

    # Load shop modules and create dedicated pages
    tasks = []
    for name in shop_names:
        try:
            module = importlib.import_module(f"shops.{name}")
            if not hasattr(module, 'scan_with_page'):
                logger.error(f"[{name}] NO scan_with_page() — skipping (needs migration)")
                continue

            # Determine browser type from module attribute
            browser_type = getattr(module, 'BROWSER_TYPE', 'standard')

            # Create dedicated page for this shop
            page = await mgr.create_page(name, browser_type=browser_type)
            if not page:
                logger.error(f"[{name}] Failed to create page — skipping")
                continue

            # Start independent worker for this shop
            tasks.append(asyncio.create_task(
                _persistent_shop_worker(name, module, page, mgr, browser_type, logger)
            ))
            logger.info(f"[{name}] Worker started ({browser_type} browser)")

        except Exception as e:
            logger.error(f"[{name}] Load failed: {e}")

    tasks.append(asyncio.create_task(heartbeat_worker(logger, process_name, len(shop_names))))

    logger.info(f"[{process_name}] {len(tasks)-1} shop workers started | Stats: {mgr.stats}")

    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except KeyboardInterrupt:
        pass
    finally:
        await mgr.close()
        await discord.close()


async def _persistent_shop_worker(name, module, page, mgr, browser_type, logger):
    """
    Independent worker for one shop with persistent page.
    
    - page lives forever (dedicated tab in persistent browser)
    - Each scan: page.goto() + parse → products
    - Self-healing: if page crashes, get new page from manager
    - No queue, no blocking, no waiting on other shops
    """
    await asyncio.sleep(random.uniform(2, 20))  # Stagger first scan

    stats = {"ok": 0, "err": 0, "consecutive_err": 0, "heal_count": 0}
    scan_fn = module.scan_with_page
    # Module can override timeout (e.g. proshop needs 180s for aggressive CF)
    SCAN_TIMEOUT = getattr(module, 'SCAN_TIMEOUT', 120 if browser_type == "stealth" else 90)

    while True:
        start = datetime.now()
        try:
            # Run scan with timeout — no shop can hang forever
            products = await asyncio.wait_for(scan_fn(page), timeout=SCAN_TIMEOUT)

            if products:
                products = sanitize_batch(products)

            if products:
                shop_field = products[0].get("shop", name)
                old = await get_shop_products(shop_field)
                snapshot = await is_snapshot_done(name)
                was_first = await detect_and_send(name, old, products, snapshot)
                if was_first or not snapshot:
                    await mark_snapshot_done(name)
                await save_products_batch(products)
                stats["ok"] += 1
                stats["err"] = 0
                stats["consecutive_err"] = 0
                stats["heal_count"] = 0  # Reset on success
                scan_time = (datetime.now() - start).total_seconds()
                logger.info(f"[{name}] {len(products)} produktow w {scan_time:.1f}s")
            else:
                stats["err"] += 1
                stats["consecutive_err"] += 1

        except asyncio.TimeoutError:
            stats["err"] += 1
            stats["consecutive_err"] += 1
            stats["heal_count"] = stats.get("heal_count", 0)

            # First try: reload (cheap, no new renderer)
            try:
                await asyncio.wait_for(page.reload(timeout=30000), timeout=35)
                logger.warning(f"[{name}] TIMEOUT {SCAN_TIMEOUT}s — reloaded page")
            except Exception:
                # Reload failed — heal only if under limit
                if stats["heal_count"] < 3:
                    stats["heal_count"] += 1
                    logger.warning(f"[{name}] TIMEOUT — heal #{stats['heal_count']}/3")
                    new_page = await mgr.heal_page(name, browser_type=browser_type)
                    if new_page:
                        page = new_page
                    else:
                        logger.error(f"[{name}] Heal failed — cooldown 30min")
                        await asyncio.sleep(1800)
                        stats["heal_count"] = 0
                        continue
                else:
                    logger.warning(f"[{name}] TIMEOUT — heal limit reached, cooldown 30min")
                    await asyncio.sleep(1800)
                    stats["heal_count"] = 0
                    continue

        except Exception as e:
            err_str = str(e)[:100]
            logger.error(f"[{name}] ERROR: {err_str}")
            stats["err"] += 1
            stats["consecutive_err"] += 1

            # Only heal on browser/page crash, with limit
            if any(x in err_str.lower() for x in ["closed", "crash", "target"]):
                stats["heal_count"] = stats.get("heal_count", 0)
                if stats["heal_count"] < 3:
                    stats["heal_count"] += 1
                    logger.warning(f"[{name}] Page crashed — heal #{stats['heal_count']}/3")
                    new_page = await mgr.heal_page(name, browser_type=browser_type)
                    if new_page:
                        page = new_page
                    else:
                        await asyncio.sleep(1800)
                        stats["heal_count"] = 0
                        continue
                else:
                    logger.warning(f"[{name}] Crash — heal limit, cooldown 30min")
                    await asyncio.sleep(1800)
                    stats["heal_count"] = 0
                    continue

        # Delay between scans (independent per shop — no blocking others)
        consec = stats["consecutive_err"]
        if consec >= 20:
            await asyncio.sleep(1800)  # 30 min
        elif consec >= 10:
            await asyncio.sleep(600)   # 10 min
        elif consec >= 5:
            await asyncio.sleep(300)   # 5 min
        elif stats["err"] > 0:
            await asyncio.sleep(random.randint(90, 180))
        else:
            # Healthy: scan every 60-120s (reduced from 30-60s to lower CPU pressure)
            # Chrome renderers are expensive — give CPU breathing room for FAST shops
            await asyncio.sleep(random.randint(60, 120))


# ============================================================
# MAIN — forks 3 processes
# ============================================================

def main():
    logger = setup_logger("MAIN")
    logger.info("=" * 60)
    logger.info("Pokemon Monitor v2 — MULTI-PROCESS Engine")
    logger.info("=" * 60)

    # Load all shops
    all_shops = load_shops()
    if not all_shops:
        logger.error("Brak sklepow!")
        return

    # Split into categories
    # Priority: module.SHOP_GROUP attribute > hardcoded sets (legacy)
    # SHOP_GROUP values: "NODRIVER", "SLOW", "VERY_SLOW", "SHOPIFY", "FAST" (default)
    fast_shops = []
    slow_shops = []
    nodriver_names = []

    for name, module in all_shops:
        # New: check module-level SHOP_GROUP (auto-classification)
        group = getattr(module, "SHOP_GROUP", None)
        if group:
            group = group.upper()
            if group == "NODRIVER":
                nodriver_names.append(name)
            elif group in ("SLOW", "VERY_SLOW", "SHOPIFY"):
                slow_shops.append((name, module))
            else:
                fast_shops.append((name, module))
        # Legacy: hardcoded sets (backward compatible)
        elif name in NODRIVER_SHOPS:
            nodriver_names.append(name)
        elif name in ALL_SLOW:
            slow_shops.append((name, module))
        else:
            fast_shops.append((name, module))

    logger.info(f"FAST: {len(fast_shops)} shops (in-process async)")
    logger.info(f"SLOW: {len(slow_shops)} shops (in-process async)")
    logger.info(f"NODRIVER: {len(nodriver_names)} shops (persistent browsers)")
    logger.info(f"ENGINES: Hydra v3 rapid pollers (separate process)")
    logger.info(f"Total: {len(all_shops)} shops in 5 independent processes")
    logger.info("Architecture: each process has OWN event loop, ZERO interference")

    # Split FAST into 2 independent processes (was 3, but 4 cores can't handle 6 processes)
    # 2 FAST + SLOW + NODRIVER + ENGINE = 5 processes on 4 cores = sustainable
    fast_chunk_size = len(fast_shops) // 2
    fast_1 = fast_shops[:fast_chunk_size]
    fast_2 = fast_shops[fast_chunk_size:]

    logger.info(f"FAST split: #{1}={len(fast_1)} | #{2}={len(fast_2)} shops")

    # Fork 5 processes (2 FAST + SLOW + NODRIVER + ENGINES)
    processes = []

    p_fast1 = multiprocessing.Process(target=run_fast_process, args=(fast_1,), name="monitor-fast-1")
    p_fast1.start()
    processes.append(p_fast1)
    logger.info(f"Started FAST-1 process (PID {p_fast1.pid}, {len(fast_1)} shops)")

    p_fast2 = multiprocessing.Process(target=run_fast_process, args=(fast_2,), name="monitor-fast-2")
    p_fast2.start()
    processes.append(p_fast2)
    logger.info(f"Started FAST-2 process (PID {p_fast2.pid}, {len(fast_2)} shops)")

    p_slow = multiprocessing.Process(target=run_slow_process, args=(slow_shops,), name="monitor-slow")
    p_slow.start()
    processes.append(p_slow)
    logger.info(f"Started SLOW process (PID {p_slow.pid})")

    p_nodriver = multiprocessing.Process(target=run_nodriver_process, args=(nodriver_names,), name="monitor-nodriver")
    p_nodriver.start()
    processes.append(p_nodriver)
    logger.info(f"Started NODRIVER process (PID {p_nodriver.pid})")

    # Hydra v3: ENGINE process (rapid API pollers)
    p_engines = multiprocessing.Process(target=run_engines_process, name="monitor-engines")
    p_engines.start()
    processes.append(p_engines)
    logger.info(f"Started ENGINES process (PID {p_engines.pid}) — Hydra v3 rapid pollers")

    # Wait for all (restart on crash)
    def signal_handler(sig, frame):
        logger.info("SIGTERM received — stopping all processes")
        for p in processes:
            p.terminate()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Monitor and restart crashed processes
    while True:
        for i, p in enumerate(processes):
            if not p.is_alive():
                logger.error(f"Process {p.name} (PID {p.pid}) CRASHED! Restarting...")
                if "fast-1" in p.name:
                    p_new = multiprocessing.Process(target=run_fast_process, args=(fast_1,), name="monitor-fast-1")
                elif "fast-2" in p.name:
                    p_new = multiprocessing.Process(target=run_fast_process, args=(fast_2,), name="monitor-fast-2")
                elif p.name == "monitor-slow":
                    p_new = multiprocessing.Process(target=run_slow_process, args=(slow_shops,), name="monitor-slow")
                elif p.name == "monitor-engines":
                    p_new = multiprocessing.Process(target=run_engines_process, name="monitor-engines")
                else:
                    p_new = multiprocessing.Process(target=run_nodriver_process, args=(nodriver_names,), name="monitor-nodriver")
                p_new.start()
                processes[i] = p_new
                logger.info(f"Restarted {p_new.name} (PID {p_new.pid})")

        import time
        time.sleep(5)


if __name__ == "__main__":
    main()
