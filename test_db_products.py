#!/usr/bin/env python3
"""Wyciaga dostepne produkty z DB dla testow botow."""
import asyncio
import asyncpg

async def main():
    pool = await asyncpg.create_pool("postgresql://pokemonitor:mon2026pg@localhost/pokemonitor", min_size=1, max_size=2)
    async with pool.acquire() as conn:
        shops = ["kartexpol", "japancollectibles", "tantis", "smyk.com", "strefa-tcg", "empik"]
        for shop in shops:
            rows = await conn.fetch(
                "SELECT id, name, url FROM products WHERE shop=$1 AND available=true LIMIT 3", shop
            )
            print(f"\n=== {shop.upper()} (available) ===")
            if not rows:
                print("  (brak dostepnych)")
            for r in rows:
                print(f"  {r['name'][:55]}")
                print(f"    {r['url']}")
    await pool.close()

asyncio.run(main())
