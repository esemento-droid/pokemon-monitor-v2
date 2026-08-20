#!/bin/bash
# Test JC Torpedo on test account (Marian Wasilewski)
# Product: Mega Heroes Mini Tin (ID=7437, 70 PLN, qty=17)
# This places a REAL order on the test account!

cd /opt/pokemon-monitor-v2

echo "=== Step 1: Warmup test session ==="
./venv/bin/python3 japancollectibles_torpedo.py warmup --test 2>&1

echo ""
echo "=== Step 2: Fire torpedo (test account, product 7437) ==="
./venv/bin/python3 japancollectibles_torpedo.py fire --test --product-id 7437 --url "https://japancollectibles.shop/Pokemon-TCG-Angielski-Mega-Heroes-Mini-Tin-p7437" 2>&1

echo ""
echo "=== Done ==="
