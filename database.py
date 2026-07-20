import aiosqlite
import json
from datetime import datetime
from config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id TEXT NOT NULL,
                shop TEXT NOT NULL,
                name TEXT,
                price TEXT,
                url TEXT,
                image TEXT,
                stock TEXT,
                available INTEGER,
                last_seen TEXT,
                created_at TEXT,
                PRIMARY KEY (id, shop)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_shop ON products(shop)")
        await db.commit()

async def get_shop_products(shop: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM products WHERE shop = ?", (shop,)
        )
        rows = await cursor.fetchall()
        result = {}
        for row in rows:
            result[row["id"]] = {
                "id": row["id"],
                "name": row["name"],
                "price": row["price"],
                "shop": row["shop"],
                "url": row["url"],
                "image": row["image"],
                "stock": json.loads(row["stock"]) if row["stock"] else None,
                "available": bool(row["available"]),
            }
        return result

async def save_products_batch(products: list):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        for p in products:
            await db.execute("""
                INSERT INTO products (id, shop, name, price, url, image, stock, available, last_seen, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id, shop) DO UPDATE SET
                    name=excluded.name,
                    price=excluded.price,
                    url=excluded.url,
                    image=excluded.image,
                    stock=excluded.stock,
                    available=excluded.available,
                    last_seen=excluded.last_seen
            """, (
                str(p["id"]), p["shop"], p["name"],
                p["price"], p["url"], p.get("image", ""),
                json.dumps(p.get("stock")), int(p.get("available", False)),
                now, now
            ))
        await db.commit()

async def cleanup_old(days=30):
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM products WHERE last_seen < ?", (cutoff,)
        )
        await db.commit()
        print(f"[CLEANUP] Usunięto {cursor.rowcount} starych rekordów")
