#!/bin/bash
# Seed thepokemania into DB + mark snapshot done + enable shop
# Run ONCE on VPS: bash infra/seed_thepokemania.sh

cd /opt/pokemon-monitor-v2

echo "=== 1. Seeding thepokemania products into DB ==="
./venv/bin/python3 -c "
import asyncio
import sys
sys.path.insert(0, '.')
from database import init_db, save_products_batch, mark_snapshot_done
from shops.thepokemania import get_products, SHOP

async def seed():
    await init_db()
    
    # Temporarily bypass SHOP_DISABLED for import
    import shops.thepokemania as mod
    mod.SHOP_DISABLED = False
    
    products = await get_products()
    if not products:
        print('ERROR: No products fetched!')
        return False
    
    print(f'Fetched {len(products)} products')
    avail = sum(1 for p in products if p.get('available'))
    oos = sum(1 for p in products if not p.get('available'))
    print(f'Available: {avail} | OOS: {oos}')
    
    # Save to DB
    count, _ = await save_products_batch(products)
    print(f'Saved {count} products to DB')
    
    # Mark snapshot done
    await mark_snapshot_done('thepokemania')
    print('Snapshot marked as done')
    
    return True

ok = asyncio.run(seed())
if not ok:
    exit(1)
"

if [ $? -ne 0 ]; then
    echo "FAILED - check errors above"
    exit 1
fi

echo ""
echo "=== 2. Enabling shop (removing SHOP_DISABLED) ==="
sed -i 's/^SHOP_DISABLED = True.*$/# SHOP_DISABLED removed by seed script/' /opt/pokemon-monitor-v2/shops/thepokemania.py
echo "Done"

echo ""
echo "=== 3. Restarting monitor ==="
sudo systemctl restart pokemon-monitor-v2
echo "Monitor restarted"

echo ""
echo "=== DONE ==="
echo "thepokemania is now active with ${avail:-?} products seeded in DB"
echo "No more Discord spam - snapshot_done=True, all products in DB"
