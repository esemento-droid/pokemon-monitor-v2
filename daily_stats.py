#!/usr/bin/env python3
"""
Daily Stats Report — sends summary to Discord at 22:00 via cron.

Cron entry:
  0 22 * * * cd /opt/pokemon-monitor-v2 && venv/bin/python daily_stats.py

Reports:
  - Total events today (NEW/RESTOCK/SOLD_OUT/PRICE_CHANGE)
  - Top shops by activity
  - Bot orders (triggered/success/failed)
  - Turbo activations
  - Active vs error shops
  - System health
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Discord webhook for stats channel
STATS_WEBHOOK_FILE = Path("/opt/pokemon-monitor-v2/discord_webhook_stats.txt")
# Fallback to main webhook
MAIN_WEBHOOK_FILE = Path("/opt/pokemon-monitor-v2/discord_webhook_jc.txt")

PG_DSN = "postgresql://pokemonitor:mon2026pg@localhost/pokemonitor"


async def get_stats():
    """Gather all stats from database."""
    import asyncpg

    conn = await asyncpg.connect(PG_DSN)
    stats = {}

    try:
        # === EVENT COUNTS TODAY ===
        row = await conn.fetchrow("""
            SELECT
                count(*) FILTER (WHERE event_type = 'NEW_PRODUCT') as new_products,
                count(*) FILTER (WHERE event_type = 'RESTOCK') as restocks,
                count(*) FILTER (WHERE event_type = 'SOLD_OUT') as sold_out,
                count(*) FILTER (WHERE event_type = 'PRICE_CHANGE') as price_changes,
                count(*) FILTER (WHERE event_type = 'SNAPSHOT') as snapshots,
                count(*) FILTER (WHERE event_type = 'BOT_TRIGGER') as bot_triggers,
                count(*) as total
            FROM event_log
            WHERE ts >= CURRENT_DATE
        """)
        stats["events"] = dict(row) if row else {}

        # === TOP SHOPS BY ACTIVITY ===
        rows = await conn.fetch("""
            SELECT shop, count(*) as cnt
            FROM event_log
            WHERE ts >= CURRENT_DATE AND event_type IN ('NEW_PRODUCT', 'RESTOCK')
            GROUP BY shop ORDER BY cnt DESC LIMIT 10
        """)
        stats["top_shops"] = [(r["shop"], r["cnt"]) for r in rows]

        # === BOT ORDERS TODAY ===
        row = await conn.fetchrow("""
            SELECT
                count(*) as total,
                count(*) FILTER (WHERE status = 'triggered') as triggered,
                count(*) FILTER (WHERE status IN ('checkout_ok', 'confirmed', 'payment_ok')) as success,
                count(*) FILTER (WHERE status = 'failed') as failed,
                count(*) FILTER (WHERE status = 'atc_ok') as atc_ok
            FROM orders
            WHERE ts >= CURRENT_DATE
        """)
        stats["orders"] = dict(row) if row else {}

        # === SHOP HEALTH ===
        row = await conn.fetchrow("""
            SELECT
                count(*) as total_shops,
                count(*) FILTER (WHERE error_count = 0) as healthy,
                count(*) FILTER (WHERE error_count >= 5) as critical
            FROM shop_state
            WHERE snapshot_done = TRUE
        """)
        stats["health"] = dict(row) if row else {}

        # === TURBO ACTIVATIONS ===
        row = await conn.fetchrow("""
            SELECT count(*) as cnt FROM shop_intel
            WHERE turbo_until IS NOT NULL AND turbo_until >= CURRENT_DATE
        """)
        stats["turbo_active"] = row["cnt"] if row else 0

        # === PRICE DROPS TODAY ===
        row = await conn.fetchrow("""
            SELECT count(*) as cnt FROM price_history WHERE ts >= CURRENT_DATE
        """)
        stats["price_changes_logged"] = row["cnt"] if row else 0

        # === LAST RESTOCK ===
        row = await conn.fetchrow("""
            SELECT shop, product_name, ts FROM event_log
            WHERE event_type = 'RESTOCK'
            ORDER BY ts DESC LIMIT 1
        """)
        stats["last_restock"] = dict(row) if row else None

        # === PRODUCTS IN DB ===
        row = await conn.fetchrow("""
            SELECT
                count(*) as total,
                count(*) FILTER (WHERE available = TRUE) as available,
                count(DISTINCT shop) as shops
            FROM products
        """)
        stats["products"] = dict(row) if row else {}

    finally:
        await conn.close()

    return stats


def format_report(stats: dict) -> str:
    """Format stats into Discord message."""
    events = stats.get("events", {})
    orders = stats.get("orders", {})
    health = stats.get("health", {})
    products = stats.get("products", {})

    now = datetime.now()
    date_str = now.strftime("%d.%m.%Y")

    lines = [
        f"📊 **DAILY REPORT — {date_str}**",
        "",
        "**📦 Events dzisiaj:**",
        f"  🆕 Nowe produkty: **{events.get('new_products', 0)}**",
        f"  🔄 Restocki: **{events.get('restocks', 0)}**",
        f"  ❌ Wyprzedane: **{events.get('sold_out', 0)}**",
        f"  💰 Zmiany cen: **{events.get('price_changes', 0)}**",
        f"  📋 Total eventów: **{events.get('total', 0)}**",
        "",
    ]

    # Top shops
    top_shops = stats.get("top_shops", [])
    if top_shops:
        lines.append("**🏪 Top sklepy (nowe + restocki):**")
        for shop, cnt in top_shops[:5]:
            lines.append(f"  • {shop}: **{cnt}**")
        lines.append("")

    # Bot orders
    if orders.get("total", 0) > 0:
        lines.append("**🤖 Boty:**")
        lines.append(f"  Triggered: {orders.get('triggered', 0)} | "
                     f"ATC OK: {orders.get('atc_ok', 0)} | "
                     f"Success: {orders.get('success', 0)} | "
                     f"Failed: {orders.get('failed', 0)}")
        lines.append("")

    # Turbo
    turbo = stats.get("turbo_active", 0)
    if turbo > 0:
        lines.append(f"⚡ Turbo activations: **{turbo}**")
        lines.append("")

    # Last restock
    last_r = stats.get("last_restock")
    if last_r:
        ts = last_r.get("ts")
        if ts:
            ago = (now - ts).total_seconds() / 60
            lines.append(f"🔄 Ostatni restock: **{last_r.get('shop', '?')}** — "
                         f"{last_r.get('product_name', '?')[:40]} ({int(ago)} min temu)")
        lines.append("")

    # Health
    lines.append("**💚 System:**")
    lines.append(f"  Sklepy: {health.get('healthy', 0)}/{health.get('total_shops', 0)} healthy | "
                 f"{health.get('critical', 0)} critical")
    lines.append(f"  Produkty w bazie: {products.get('total', 0)} ({products.get('available', 0)} dostępnych)")
    lines.append(f"  Monitorowane sklepy: {products.get('shops', 0)}")

    return "\n".join(lines)


async def send_report():
    """Generate and send daily report."""
    import aiohttp

    # Get webhook URL
    webhook_url = ""
    if STATS_WEBHOOK_FILE.exists():
        webhook_url = STATS_WEBHOOK_FILE.read_text().strip()
    if not webhook_url and MAIN_WEBHOOK_FILE.exists():
        webhook_url = MAIN_WEBHOOK_FILE.read_text().strip()
    if not webhook_url:
        print("ERROR: No webhook URL found")
        return

    # Gather stats
    try:
        stats = await get_stats()
    except Exception as e:
        print(f"ERROR gathering stats: {e}")
        # Send error report
        async with aiohttp.ClientSession() as s:
            await s.post(webhook_url, json={
                "content": f"⚠️ **DAILY STATS ERROR**\n{e}"
            })
        return

    # Format
    report = format_report(stats)
    print(report)

    # Send to Discord
    async with aiohttp.ClientSession() as s:
        # Discord has 2000 char limit per message
        if len(report) > 1900:
            parts = report.split("\n\n")
            msg = ""
            for part in parts:
                if len(msg) + len(part) + 2 > 1900:
                    await s.post(webhook_url, json={"content": msg})
                    msg = part + "\n\n"
                    await asyncio.sleep(1)
                else:
                    msg += part + "\n\n"
            if msg.strip():
                await s.post(webhook_url, json={"content": msg})
        else:
            await s.post(webhook_url, json={"content": report})

    print("Report sent!")


if __name__ == "__main__":
    asyncio.run(send_report())
