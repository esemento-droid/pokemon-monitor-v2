#!/usr/bin/env python3
"""Runner - uruchamia jeden scraper w osobnym procesie."""
_T0 = __import__("time").time()
import sys
import os
import asyncio
import json
import time
import importlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import init_db, get_shop_products, save_products_batch, is_snapshot_done, mark_snapshot_done
from detector import detect_and_send
from discord_sender import discord
from sanitize import sanitize_batch

async def run_shop(name):
    await init_db()
    discord.start()

    module = importlib.import_module(f"shops.{name}")
    get_fn = module.get_products

    print(f"[{name}] READY in {time.time()-_T0:.1f}s", flush=True)
    start = time.time()
    if asyncio.iscoroutinefunction(get_fn):
        products = await get_fn()
    else:
        products = get_fn()

    if not products:
        print(f"[{name}] 0 produktow", flush=True)
        await discord.close()
        return

    products = sanitize_batch(products)
    if not products:
        await discord.close()
        return

    shop_field = products[0].get("shop", name)
    old = await get_shop_products(shop_field)

    if not products and old:
        await discord.close()
        return

    snapshot_done = await is_snapshot_done(name)
    was_first = await detect_and_send(name, old, products, snapshot_done)
    if was_first or not snapshot_done:
        await mark_snapshot_done(name)

    await save_products_batch(products)

    elapsed = time.time() - start
    print(f"[{name}] {len(products)} produktow w {elapsed:.1f}s", flush=True)

    await asyncio.sleep(1)
    await discord.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: runner.py <shopname>")
        sys.exit(1)
    asyncio.run(run_shop(sys.argv[1]))
