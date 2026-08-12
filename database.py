import asyncpg
import json
import logging
import asyncio
from datetime import datetime
from typing import Optional, List, Dict

logger = logging.getLogger("monitor")
_pool = None
PG_DSN = "postgresql://pokemonitor:mon2026pg@localhost/pokemonitor"

async def init_db():
    global _pool
    if _pool is not None:
        return
    _pool = await asyncpg.create_pool(PG_DSN, min_size=2, max_size=10)
    async with _pool.acquire() as conn:
        # === CORE TABLES ===
        await conn.execute("""CREATE TABLE IF NOT EXISTS products (
            id TEXT NOT NULL, shop TEXT NOT NULL, name TEXT, price TEXT,
            url TEXT, image TEXT, stock TEXT, available BOOLEAN DEFAULT FALSE,
            last_seen TIMESTAMP, created_at TIMESTAMP, PRIMARY KEY (id, shop))""")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_shop ON products(shop)")

        await conn.execute("""CREATE TABLE IF NOT EXISTS shop_state (
            shop TEXT PRIMARY KEY, snapshot_done BOOLEAN DEFAULT FALSE,
            last_scan TIMESTAMP, scan_count INTEGER DEFAULT 0, error_count INTEGER DEFAULT 0)""")

        # === EVENT LOG — historia KAŻDEGO eventu (fundament inteligencji) ===
        await conn.execute("""CREATE TABLE IF NOT EXISTS event_log (
            id SERIAL PRIMARY KEY,
            ts TIMESTAMP NOT NULL DEFAULT NOW(),
            shop TEXT NOT NULL,
            product_id TEXT,
            product_name TEXT,
            event_type TEXT NOT NULL,
            price TEXT,
            url TEXT,
            metadata JSONB,
            CONSTRAINT event_log_type_check CHECK (
                event_type IN ('NEW_PRODUCT','RESTOCK','SOLD_OUT','PRICE_CHANGE','SNAPSHOT','BOT_TRIGGER','BOT_SUCCESS','BOT_FAIL','ERROR')
            ))""")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_event_ts ON event_log(ts DESC)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_event_shop ON event_log(shop, ts DESC)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_event_type ON event_log(event_type, ts DESC)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_event_product ON event_log(product_id, shop)")

        # === PRICE HISTORY — śledzenie zmian cen w czasie ===
        await conn.execute("""CREATE TABLE IF NOT EXISTS price_history (
            id SERIAL PRIMARY KEY,
            ts TIMESTAMP NOT NULL DEFAULT NOW(),
            shop TEXT NOT NULL,
            product_id TEXT NOT NULL,
            product_name TEXT,
            old_price TEXT,
            new_price TEXT,
            price_numeric NUMERIC)""")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_price_product ON price_history(product_id, shop, ts DESC)")

        # === ORDERS — tracking zamówień botów ===
        await conn.execute("""CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            ts TIMESTAMP NOT NULL DEFAULT NOW(),
            shop TEXT NOT NULL,
            account_email TEXT NOT NULL,
            product_id TEXT,
            product_name TEXT,
            product_url TEXT,
            qty INTEGER DEFAULT 1,
            price TEXT,
            status TEXT DEFAULT 'triggered',
            order_number TEXT,
            error_msg TEXT,
            metadata JSONB,
            CONSTRAINT orders_status_check CHECK (
                status IN ('triggered','atc_ok','checkout_ok','payment_ok','confirmed','failed','cancelled')
            ))""")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_shop ON orders(shop, ts DESC)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_account ON orders(account_email, ts DESC)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")

        # === SHOP INTELLIGENCE — dane do predykcji i korelacji ===
        await conn.execute("""CREATE TABLE IF NOT EXISTS shop_intel (
            shop TEXT PRIMARY KEY,
            avg_restock_interval_min NUMERIC,
            last_restock_ts TIMESTAMP,
            total_restocks INTEGER DEFAULT 0,
            total_new_products INTEGER DEFAULT 0,
            peak_hours JSONB,
            correlated_shops JSONB,
            scan_speed_mode TEXT DEFAULT 'normal',
            turbo_until TIMESTAMP,
            metadata JSONB)""")


# ============================================================
# CORE FUNCTIONS (backwards compatible)
# ============================================================

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


# ============================================================
# EVENT LOG — zapis każdego eventu
# ============================================================

async def log_event(shop: str, event_type: str, product_id: str = None,
                    product_name: str = None, price: str = None,
                    url: str = None, metadata: dict = None):
    """Log ANY event to database. Foundation for intelligence."""
    try:
        meta_json = json.dumps(metadata) if metadata else None
        async with _pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO event_log (shop, product_id, product_name, event_type, price, url, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            """, shop, product_id, product_name, event_type, price, url, meta_json)
    except Exception as e:
        logger.error(f"[DB] log_event error: {e}")


async def log_price_change(shop: str, product_id: str, product_name: str,
                           old_price: str, new_price: str):
    """Record price change for history tracking."""
    try:
        # Try to parse numeric price for analytics
        price_num = None
        try:
            price_clean = new_price.replace("PLN", "").replace("zł", "").replace("zl", "").replace(",", ".").replace(" ", "").strip()
            price_num = float(price_clean)
        except (ValueError, TypeError):
            pass

        async with _pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO price_history (shop, product_id, product_name, old_price, new_price, price_numeric)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, shop, product_id, product_name, old_price, new_price, price_num)
    except Exception as e:
        logger.error(f"[DB] log_price_change error: {e}")


# ============================================================
# ORDERS — tracking zamówień botów
# ============================================================

async def log_order(shop: str, account_email: str, product_id: str = None,
                    product_name: str = None, product_url: str = None,
                    qty: int = 1, price: str = None, status: str = "triggered",
                    metadata: dict = None) -> Optional[int]:
    """Log bot order. Returns order ID."""
    try:
        meta_json = json.dumps(metadata) if metadata else None
        async with _pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO orders (shop, account_email, product_id, product_name, product_url, qty, price, status, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
                RETURNING id
            """, shop, account_email, product_id, product_name, product_url, qty, price, status, meta_json)
            return row["id"] if row else None
    except Exception as e:
        logger.error(f"[DB] log_order error: {e}")
        return None


async def update_order_status(order_id: int, status: str, order_number: str = None,
                              error_msg: str = None):
    """Update order status (atc_ok → checkout_ok → confirmed / failed)."""
    try:
        async with _pool.acquire() as conn:
            await conn.execute("""
                UPDATE orders SET status = $2, order_number = COALESCE($3, order_number),
                error_msg = COALESCE($4, error_msg)
                WHERE id = $1
            """, order_id, status, order_number, error_msg)
    except Exception as e:
        logger.error(f"[DB] update_order error: {e}")


# ============================================================
# SHOP INTELLIGENCE — queries for smart decisions
# ============================================================

async def get_last_restock(shop: str) -> Optional[datetime]:
    """When was the last restock for this shop?"""
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT ts FROM event_log
                WHERE shop = $1 AND event_type = 'RESTOCK'
                ORDER BY ts DESC LIMIT 1
            """, shop)
            return row["ts"] if row else None
    except Exception:
        return None


async def get_restock_count_24h(shop: str) -> int:
    """How many restocks in last 24h for this shop?"""
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT count(*) as cnt FROM event_log
                WHERE shop = $1 AND event_type = 'RESTOCK'
                AND ts > NOW() - INTERVAL '24 hours'
            """, shop)
            return row["cnt"] if row else 0
    except Exception:
        return 0


async def get_recent_events(shop: str = None, event_type: str = None,
                            minutes: int = 10, limit: int = 50) -> List[Dict]:
    """Get recent events for analysis/correlation."""
    try:
        async with _pool.acquire() as conn:
            query = "SELECT * FROM event_log WHERE ts > NOW() - ($1 || ' minutes')::INTERVAL"
            params = [str(minutes)]
            idx = 2
            if shop:
                query += f" AND shop = ${idx}"
                params.append(shop)
                idx += 1
            if event_type:
                query += f" AND event_type = ${idx}"
                params.append(event_type)
                idx += 1
            query += " ORDER BY ts DESC LIMIT $" + str(idx)
            params.append(limit)
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]
    except Exception:
        return []


async def should_turbo_mode(shop: str) -> bool:
    """Check if shop should be in turbo mode (recent activity on correlated shops)."""
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT turbo_until FROM shop_intel WHERE shop = $1
            """, shop)
            if row and row["turbo_until"]:
                return row["turbo_until"] > datetime.now()
            return False
    except Exception:
        return False


async def activate_turbo_mode(shop: str, duration_minutes: int = 10):
    """Activate turbo mode for a shop (scan faster)."""
    try:
        async with _pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO shop_intel (shop, turbo_until, scan_speed_mode)
                VALUES ($1, NOW() + ($2 || ' minutes')::INTERVAL, 'turbo')
                ON CONFLICT(shop) DO UPDATE SET
                    turbo_until = NOW() + ($2 || ' minutes')::INTERVAL,
                    scan_speed_mode = 'turbo'
            """, shop, str(duration_minutes))
    except Exception as e:
        logger.error(f"[DB] activate_turbo error: {e}")


async def record_restock(shop: str):
    """Record restock event in shop_intel for statistics."""
    try:
        async with _pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO shop_intel (shop, last_restock_ts, total_restocks)
                VALUES ($1, NOW(), 1)
                ON CONFLICT(shop) DO UPDATE SET
                    last_restock_ts = NOW(),
                    total_restocks = shop_intel.total_restocks + 1
            """, shop)
    except Exception as e:
        logger.error(f"[DB] record_restock error: {e}")

