import asyncpg
import json
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger("monitor")
_pool = None
PG_DSN = "postgresql://pokemonitor:mon2026pg@localhost/pokemonitor"

async def init_db():
    global _pool
    if _pool is not None:
        return
    _pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=3)
    async with _pool.acquire() as conn:
        await conn.execute("""CREATE TABLE IF NOT EXISTS products (
            id TEXT NOT NULL, shop TEXT NOT NULL, name TEXT, price TEXT,
            url TEXT, image TEXT, stock TEXT, available BOOLEAN DEFAULT FALSE,
            last_seen TIMESTAMP, created_at TIMESTAMP, PRIMARY KEY (id, shop))""")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_shop ON products(shop)")
        await conn.execute("""CREATE TABLE IF NOT EXISTS shop_state (
            shop TEXT PRIMARY KEY, snapshot_done BOOLEAN DEFAULT FALSE,
            last_scan TIMESTAMP, scan_count INTEGER DEFAULT 0, error_count INTEGER DEFAULT 0)""")

async def get_shop_products(shop):
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM products WHERE shop = $1", shop)
    result = {}
    for row in rows:
        stock_val = row["stock"]
        if stock_val:
            try:
                stock_val = json.loads(stock_val)
            except:
                pass
        result[row["id"]] = {"id": row["id"], "name": row["name"], "price": row["price"], "shop": row["shop"], "url": row["url"], "image": row["image"], "stock": stock_val, "available": bool(row["available"])}
    return result

async def save_products_batch(products):
    now = datetime.now()
    rows = []
    for p in products:
        try:
            sv = p.get("stock")
            if isinstance(sv, list):
                sv = sv[0] if sv else None
            iv = p.get("image", "")
            if isinstance(iv, list):
                p["image"] = iv[0] if iv else ""
            sj = json.dumps(sv) if isinstance(sv, (int, float, bool, str)) else json.dumps(None)
            rows.append((str(p["id"]), p["shop"], p["name"], p["price"], p["url"], p.get("image", ""), sj, bool(p.get("available", False)), now, now))
        except Exception as e:
            logger.error(f"[DB] prep: {e}")
    if rows:
        async with _pool.acquire() as conn:
            await conn.executemany("INSERT INTO products (id,shop,name,price,url,image,stock,available,last_seen,created_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) ON CONFLICT(id,shop) DO UPDATE SET name=EXCLUDED.name, price=EXCLUDED.price, url=EXCLUDED.url, image=EXCLUDED.image, stock=EXCLUDED.stock, available=EXCLUDED.available, last_seen=EXCLUDED.last_seen", rows)
    return len(rows), 0

async def is_snapshot_done(shop):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT snapshot_done FROM shop_state WHERE shop = $1", shop)
        return row["snapshot_done"] if row else False

async def mark_snapshot_done(shop):
    async with _pool.acquire() as conn:
        await conn.execute("INSERT INTO shop_state (shop, snapshot_done) VALUES ($1, TRUE) ON CONFLICT(shop) DO UPDATE SET snapshot_done = TRUE", shop)

async def update_shop_state(shop, success=True):
    async with _pool.acquire() as conn:
        if success:
            await conn.execute("INSERT INTO shop_state (shop, last_scan, scan_count, error_count) VALUES ($1, NOW(), 1, 0) ON CONFLICT(shop) DO UPDATE SET last_scan = NOW(), scan_count = shop_state.scan_count + 1, error_count = 0", shop)
        else:
            await conn.execute("INSERT INTO shop_state (shop, error_count) VALUES ($1, 1) ON CONFLICT(shop) DO UPDATE SET error_count = shop_state.error_count + 1", shop)
