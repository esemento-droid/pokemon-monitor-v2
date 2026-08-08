import asyncio
import os
import importlib
import random
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from config import CHECK_MIN, CHECK_MAX, LOG_PATH, DISCORD_WEBHOOK
from database import init_db, get_shop_products, save_products_batch
from detector import detect_and_send
from discord_sender import discord
from sanitize import sanitize_batch

logger = logging.getLogger("monitor")
logger.setLevel(logging.INFO)
fh = RotatingFileHandler(LOG_PATH, maxBytes=5*1024*1024, backupCount=3)
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(fh)
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(ch)

snapshot_done = set()
scan_stats = {}

SLOW_SHOPS = set()
MEDIUM_SLOW_SHOPS = {"piwniczaki", "strefa-tcg", "basanti", "blindbox", "dragonus", "dvdmax", "flamberg", "hearts", "pikashop", "tantis", "wilczek"}
PLAYWRIGHT_SHOPS = {"basanti", "blindbox", "dragonus", "dvdmax", "flamberg", "hearts", "pikashop", "piwniczaki", "tantis", "wilczek"}
pw_semaphore = None


def load_shops():
    shops = []
    shops_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shops")
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
                logger.info(f"[LOAD] + {name}")
        except Exception as e:
            logger.error(f"[LOAD] X {name}: {e}", exc_info=True)
    logger.info(f"[LOAD] Aktywne sklepy: {len(shops)}")
    return shops


async def heartbeat_worker():
    import aiohttp
    await asyncio.sleep(30)
    while True:
        try:
            shops_ok = sum(1 for s in scan_stats.values() if s["ok"] > 0)
            total = sum(s["ok"] + s["err"] for s in scan_stats.values())
            async with aiohttp.ClientSession() as session:
                await session.post(DISCORD_WEBHOOK, json={"content": f"Heartbeat: {shops_ok} sklepow OK, {total} skanow"})
        except:
            pass
        await asyncio.sleep(21600)


async def shop_worker(name, module):
    await asyncio.sleep(random.uniform(0, 30))
    scan_stats[name] = {"ok": 0, "err": 0, "last": None}
    while True:
        try:
            start = datetime.now()
            products = None
            for _attempt in range(3):
                try:
                    get_fn = module.get_products
                    if name in PLAYWRIGHT_SHOPS and pw_semaphore:
                        async with pw_semaphore:
                            if asyncio.iscoroutinefunction(get_fn):
                                products = await get_fn()
                            else:
                                products = await asyncio.get_event_loop().run_in_executor(None, get_fn)
                    else:
                        if asyncio.iscoroutinefunction(get_fn):
                            products = await get_fn()
                        else:
                            products = await asyncio.get_event_loop().run_in_executor(None, get_fn)
                    break
                except Exception as _re:
                    if _attempt < 2:
                        await asyncio.sleep(15 * (2 ** _attempt))
                    else:
                        raise
            if not products:
                scan_stats[name]["err"] += 1
            else:
                products = sanitize_batch(products)
                shop_field = products[0].get("shop", name) if products else name
                old = await get_shop_products(shop_field)
                if not products and old:
                    logger.warning(f"[{name}] 0 produktow ale DB ma {len(old)} - pomijam")
                    scan_stats[name]["ok"] += 1
                    continue
                was_first = await detect_and_send(name, old, products, name in snapshot_done)
                if was_first or name not in snapshot_done:
                    snapshot_done.add(name)
                await save_products_batch(products)
                elapsed = (datetime.now() - start).total_seconds()
                logger.info(f"[{name}] {len(products)} produktow w {elapsed:.1f}s")
                scan_stats[name]["ok"] += 1
                scan_stats[name]["err"] = 0
                scan_stats[name]["last"] = datetime.now().isoformat()
        except Exception as e:
            logger.error(f"[{name}] CRITICAL: {e}", exc_info=True)
            scan_stats[name]["err"] += 1
            threshold = 15 if name in SLOW_SHOPS else (10 if name in MEDIUM_SLOW_SHOPS else 5)
            if scan_stats[name]["err"] == threshold or (scan_stats[name]["err"] > threshold and scan_stats[name]["err"] % (threshold * 2) == 0):
                try:
                    import aiohttp
                    async with aiohttp.ClientSession() as s:
                        await s.post(DISCORD_WEBHOOK, json={"content": f"ALARM [{name}] {e}"})
                except:
                    pass
        errs = scan_stats[name]["err"]
        mult = min(2 ** (errs // 5), 4) if errs >= 5 else 1
        if name in SLOW_SHOPS:
            delay = random.randint(180 * mult, 360 * mult)
        elif name in MEDIUM_SLOW_SHOPS:
            delay = random.randint(45 * mult, 90 * mult)
        else:
            delay = random.randint(CHECK_MIN * mult, CHECK_MAX * mult)
        await asyncio.sleep(delay)


async def main():
    logger.info("=" * 50)
    logger.info("Pokemon Monitor v2 TURBO - START")
    global pw_semaphore
    pw_semaphore = asyncio.Semaphore(1)
    await init_db()
    shops = load_shops()
    if not shops:
        logger.error("Brak sklepow!")
        return
    tasks = []
    for name, module in shops:
        tasks.append(asyncio.create_task(shop_worker(name, module)))
    tasks.append(asyncio.create_task(heartbeat_worker()))
    logger.info(f"Uruchomiono {len(shops)} niezaleznych workerow + heartbeat")
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Zatrzymywanie...")
    finally:
        await discord.close()


if __name__ == "__main__":
    asyncio.run(main())
