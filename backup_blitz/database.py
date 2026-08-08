import aiosqlite
import json
import logging
import asyncio
from datetime import datetime
from config import DB_PATH

logger = logging.getLogger("monitor")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=10000")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("""CREATE TABLE IF NOT EXISTS products (
            id TEXT NOT NULL, shop TEXT NOT NULL, name TEXT, price TEXT,
            url TEXT, image TEXT, stock TEXT, available INTEGER,
            last_seen TEXT, created_at TEXT, PRIMARY KEY (id, shop))""")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_shop ON products(shop)")
        await db.commit()

async def get_shop_products(shop):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=10000")
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM products WHERE shop = ?", (shop,))
        rows = await cursor.fetchall()
    result = {}
    for row in rows:
        stock_val = row["stock"]
        if stock_val:
            try:
                stock_val = json.loads(stock_val)
            except:
                pass
        result[row["id"]] = {
            "id": row["id"], "name": row["name"], "price": row["price"],
            "shop": row["shop"], "url": row["url"], "image": row["image"],
            "stock": stock_val, "available": bool(row["available"])
        }
    return result

async def save_products_batch(products):
    now = datetime.now().isoformat()
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
            rows.append((str(p["id"]), p["shop"], p["name"], p["price"],
                        p["url"], p.get("image", ""), sj,
                        int(p.get("available", False)), now, now))
        except Exception as e:
            logger.error(f"[DB] prep: {e}")
    if rows:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("PRAGMA busy_timeout=10000")
            await db.execute("PRAGMA synchronous=NORMAL")
            await db.executemany(
                "INSERT INTO products (id,shop,name,price,url,image,stock,available,last_seen,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id,shop) DO UPDATE SET "
                "name=excluded.name,price=excluded.price,url=excluded.url,"
                "image=excluded.image,stock=excluded.stock,available=excluded.available,"
                "last_seen=excluded.last_seen", rows)
            await db.commit()
    return len(rows), 0
