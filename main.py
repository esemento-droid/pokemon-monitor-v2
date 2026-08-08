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


# Sklepy z niestabilnym SSL - dluzszy timeout ale NIE wolniejszy delay
UNSTABLE_SSL = {"futurex", "tcgheaven", "graal", "kantodrop", "tcgumisia", "strefa-tcg"}


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
        except Exception as e:
            logger.error(f"[LOAD] X {name}: {e}")
    logger.info(f"[LOAD] Aktywne sklepy: {len(shops)}")
    return shops



async def heartbeat_worker():
    import aiohttp
    await asyncio.sleep(60)
    while True:
        try:
            shops_ok = sum(1 for s in scan_stats.values() if s["ok"] > 0)
            total_scans = sum(s["ok"] + s["err"] for s in scan_stats.values())
            errors = sum(1 for s in scan_stats.values() if s["err"] > 0)
            async with aiohttp.ClientSession() as session:
                await session.post(DISCORD_WEBHOOK, json={
                    "content": f"\u2764\ufe0f Heartbeat: {shops_ok} sklepow OK, {total_scans} skanow, {errors} z bledami"
                })
        except:
            pass
        await asyncio.sleep(21600)


async def shop_worker(name, module):
    await asyncio.sleep(random.uniform(0, 90))
    scan_stats[name] = {"ok": 0, "err": 0, "last": None}

    while True:
        try:
            start = datetime.now()
            products = None

            # Single attempt with proper timeout - no retries blocking for minutes
            try:
                get_fn = module.get_products
                if asyncio.iscoroutinefunction(get_fn):
                        products = await asyncio.wait_for(get_fn(), timeout=60)
                else:
                    products = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(None, get_fn),
                        timeout=60
                    )
            except asyncio.TimeoutError:
                logger.warning(f"[{name}] Timeout 60s")
                scan_stats[name]["err"] += 1
                await asyncio.sleep(random.randint(CHECK_MIN, CHECK_MAX))
                continue
            except Exception as e:
                raise

            if not products:
                scan_stats[name]["err"] += 1
                await asyncio.sleep(random.randint(CHECK_MIN, CHECK_MAX))
                continue

            products = sanitize_batch(products)
            if not products:
                scan_stats[name]["err"] += 1
                await asyncio.sleep(random.randint(CHECK_MIN, CHECK_MAX))
                continue

            shop_field = products[0].get("shop", name)
            old = await get_shop_products(shop_field)

            if not products and old:
                logger.warning(f"[{name}] 0 produktow ale DB ma {len(old)} - pomijam")
                scan_stats[name]["ok"] += 1
                await asyncio.sleep(random.randint(CHECK_MIN, CHECK_MAX))
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
            logger.error(f"[{name}] ERROR: {e}")
            scan_stats[name]["err"] += 1

            # Alarm po 5 errorach z rzedu
            if scan_stats[name]["err"] == 5:
                try:
                    import aiohttp
                    async with aiohttp.ClientSession() as s:
                        await s.post(DISCORD_WEBHOOK, json={
                            "content": f"\u26a0\ufe0f ALARM [{name}] 5 errorow z rzedu: {e}"
                        })
                except:
                    pass

        # Delay - prosty i szybki
        errs = scan_stats[name]["err"]
        if errs >= 5:
            delay = random.randint(60, 120)  # backoff po errorach
        else:
            delay = random.randint(5, 30)
        await asyncio.sleep(delay)



async def main():
    logger.info("=" * 50)
    logger.info("Pokemon Monitor v2 BLITZ - START")

    await init_db()
    discord.start()

    shops = load_shops()
    if not shops:
        logger.error("Brak sklepow!")
        return

    tasks = []
    for name, module in shops:
        tasks.append(asyncio.create_task(shop_worker(name, module)))
    tasks.append(asyncio.create_task(heartbeat_worker()))

    logger.info(f"Uruchomiono {len(shops)} niezaleznych workerow + heartbeat")
    logger.info("Architektura: zero lockow, zero kolejek, kazdy worker niezalezny")
    logger.info(f"Delay: {CHECK_MIN}-{CHECK_MAX}s, Discord: fire-and-forget queue")

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Zatrzymywanie...")
    finally:
        await discord.close()


if __name__ == "__main__":
    asyncio.run(main())
