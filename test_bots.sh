#!/bin/bash
cd /opt/pokemon-monitor-v2
export DISPLAY=:99

echo "=== TEST BOTOW NA REALNYCH PRODUKTACH ==="
echo ""

echo "--- 1. KARTEXPOL ---"
timeout 120 venv/bin/python3 -u kartexpol_autobuy.py --test --accounts 1 "https://www.kartexpol.pl/pl/p/Pokemon-TCG-Ninja-Spinner-Booster-Box-m4/171" 2>&1 | tail -10
echo ""

echo "--- 2. SMYK ---"
timeout 120 venv/bin/python3 -u smyk_autobuy.py --test "https://www.smyk.com/pl/pl/p/pokemon-tcg-battle-academy-zestaw-startowy-gra-karciana-i7823723" 2>&1 | tail -10
echo ""

echo "--- 3. TANTIS ---"
timeout 120 venv/bin/python3 -u tantis_autobuy.py --test --accounts 1 "3776398" 2>&1 | tail -10
echo ""

echo "--- 4. STREFATCG ---"
timeout 120 venv/bin/python3 -u strefatcg_autobuy.py --test --accounts 1 "https://strefa-tcg.pl/pl/p/3-Pack-Blister-Binacle/7385" 2>&1 | tail -10
echo ""

echo "--- 5. JAPANCOLLECTIBLES ---"
timeout 120 venv/bin/python3 -u japancollectibles_autobuy.py --test --accounts 1 --qty 1 "https://japancollectibles.shop/Pokemon-TCG-Angielski-Kanto-Friends-Mini-Tin-p7589" 2>&1 | tail -10
echo ""

echo "=== DONE ==="
