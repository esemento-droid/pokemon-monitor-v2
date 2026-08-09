#!/usr/bin/env python3
import asyncio, asyncpg

async def main():
    pool = await asyncpg.create_pool("postgresql://pokemonitor:mon2026pg@localhost/pokemonitor", min_size=1, max_size=2)
    async with pool.acquire() as conn:
        print("=== AM76 ===")
        rows = await conn.fetch("SELECT name, price, available FROM products WHERE shop=$1 ORDER BY last_seen DESC LIMIT 15", "am76")
        for r in rows:
            print(f"  {r['name'][:60]} | {r['price']} | avail={r['available']}")
        print()
        print("=== BATTLESTASH ===")
        rows = await conn.fetch("SELECT name, price, available FROM products WHERE shop=$1 ORDER BY last_seen DESC LIMIT 15", "battlestash.pl")
        for r in rows:
            print(f"  {r['name'][:60]} | {r['price']} | avail={r['available']}")
    await pool.close()

asyncio.run(main())
