#!/usr/bin/env python3
import asyncio, asyncpg

async def q():
    c = await asyncpg.connect("postgresql://pokemonitor:mon2026pg@localhost/pokemonitor")
    rows = await c.fetch("SELECT name,available,price,image FROM products WHERE shop='battlestash.pl' ORDER BY available DESC LIMIT 15")
    for r in rows:
        s = "V" if r["available"] else "X"
        img = "IMG" if r["image"] else "NO"
        print(f"{s} {img} {r['price'] or '?':>12} {r['name'][:55]}")
    t = await c.fetchval("SELECT count(*) FROM products WHERE shop='battlestash.pl'")
    a = await c.fetchval("SELECT count(*) FROM products WHERE shop='battlestash.pl' AND available=true")
    print(f"TOTAL:{t} AVAIL:{a}")
    await c.close()

asyncio.run(q())
