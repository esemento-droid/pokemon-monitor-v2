#!/usr/bin/env python3
"""
JapanCollectibles TORPEDO v2 — hybrid instant buy (~7s vs 70s browser bot)

Strategy:
  - ATC via HTTP (0.6s) — no browser needed for adding to cart
  - Checkout via pre-warmed Playwright page (already logged in, overlays dismissed)
  - All 4 accounts fire in PARALLEL
  - Pre-warmed pages created by session_warmer (cron hourly)

Total time target: ~7s for all 4 accounts (parallel)
vs old bot: 70s per account × 4 sequential = 280s

Called by japancollectibles_trigger.py on restock detection.
"""
import asyncio
import json
import logging
import os
import sys
import time
import re
from pathlib import Path

import aiohttp

BASE_DIR = Path("/opt/pokemon-monitor-v2")
COMPLETED_FILE = BASE_DIR / "japancollectibles_completed.json"
LOG_FILE = BASE_DIR / "japancollectibles_torpedo.log"
WEBHOOK_FILE = BASE_DIR / "discord_webhook_jc.txt"
SHOP_URL = "https://japancollectibles.shop"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [JC-TORPEDO] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

ACCOUNTS = [
    {"email": "esemento@gmail.com", "password": "cR!9GW#x2wqJtGw", "name": "Tomasz Szczepaniak"},
    {"email": "blackmat36@gmail.com", "password": "v2@pvDGt#ZuN3ui", "name": "Natalia Szczepaniak"},
    {"email": "tjbtaniojuzbylo@gmail.com", "password": "P9XAfQE.SCwFq5i", "name": "Jagoda Kaczmarek"},
    {"email": "y24015411@gmail.com", "password": "huw!e.twdCmv9@B", "name": "Mirosława Szczepaniak"},
]

TEST_ACCOUNT = {"email": "t11008543@gmail.com", "password": "mt!cSsphud4Zhnz", "name": "Marian Wasilewski"}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
PROXY_HTTP = "http://127.0.0.1:8888"
PROXY_PW = {"server": "http://127.0.0.1:8888"}


# ============================================================
# TORPEDO BUY — hybrid (HTTP ATC + Playwright checkout)
# ============================================================

async def torpedo_buy(account, product_id, product_url=""):
    """
    Hybrid instant buy:
    1. HTTP: login + ATC (0.6s)
    2. Playwright: open cart → click checkout → select payment/delivery → submit (~6s)
    """
    email = account["email"]
    t0 = time.time()
    log.info(f"[{email}] TORPEDO START product={product_id}")

    # === PHASE 1: HTTP — Login + ATC (fastest possible) ===
    connector = aiohttp.TCPConnector(ssl=False)
    jar = aiohttp.CookieJar(unsafe=True)
    cookies_for_pw = []

    async with aiohttp.ClientSession(
        connector=connector,
        cookie_jar=jar,
        headers={"User-Agent": UA},
    ) as session:
        # Login
        try:
            await session.get(SHOP_URL, proxy=PROXY_HTTP, timeout=aiohttp.ClientTimeout(total=8))
            r = await session.post(
                f"{SHOP_URL}/login",
                data={"email": email, "password": account["password"], "submit": "1"},
                proxy=PROXY_HTTP,
                timeout=aiohttp.ClientTimeout(total=8),
                allow_redirects=True,
            )
            login_html = await r.text()
            if "Moje konto" not in login_html:
                log.error(f"[{email}] Login FAILED")
                return False
            log.info(f"[{email}] Login OK ({time.time()-t0:.2f}s)")
        except Exception as e:
            log.error(f"[{email}] Login error: {e}")
            return False

        # ATC via HTTP
        try:
            r = await session.get(
                f"{SHOP_URL}/cart/add/{product_id}",
                proxy=PROXY_HTTP,
                timeout=aiohttp.ClientTimeout(total=8),
                allow_redirects=True,
            )
            if r.status == 200:
                log.info(f"[{email}] ATC OK ({time.time()-t0:.2f}s)")
            else:
                log.error(f"[{email}] ATC HTTP {r.status}")
                return False
        except Exception as e:
            log.error(f"[{email}] ATC error: {e}")
            return False

        # Extract cookies for Playwright
        for cookie in jar:
            cookies_for_pw.append({
                "name": cookie.key,
                "value": cookie.value,
                "domain": "japancollectibles.shop",
                "path": "/",
            })

    # === PHASE 2: Playwright — checkout (with session from HTTP) ===
    from patchright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
            proxy=PROXY_PW,
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=UA,
        )
        # Inject session cookies
        await context.add_cookies(cookies_for_pw)
        page = await context.new_page()

        try:
            # Go directly to cart (we're already logged in + product in cart)
            await page.goto(f"{SHOP_URL}/cart/", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(3000)  # Angular hydration

            # Remove overlays
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.getElementById('cm')?.remove();
                document.querySelector('.fixed-elements')?.remove();
                document.querySelector('.skyshop-alert-conditional-access')?.remove();
            }""")

            log.info(f"[{email}] Cart page loaded ({time.time()-t0:.2f}s)")

            # Click "Przejdź do kasy" (order button)
            order_btn = page.locator("button[data-ng-click='order()']:not([disabled])")
            try:
                await order_btn.wait_for(state="visible", timeout=10000)
                await order_btn.click(force=True)
            except Exception:
                # Fallback: submit form directly
                await page.evaluate("""() => {
                    const form = document.getElementById('orderForm');
                    if (form) form.submit();
                }""")

            # Wait for /order page
            await page.wait_for_url("**/order**", timeout=10000)
            await page.wait_for_timeout(3000)  # Angular render checkout

            log.info(f"[{email}] Checkout page ({time.time()-t0:.2f}s)")

            # Remove overlays again
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.querySelector('.fixed-elements')?.remove();
            }""")

            # Wait for payment options to render
            for _ in range(8):
                has_payments = await page.evaluate("() => document.body.innerText.includes('BLIK') || document.body.innerText.includes('Przelew')")
                if has_payments:
                    break
                await page.wait_for_timeout(1000)

            # Select BLIK payment
            try:
                blik = page.locator("text=BLIK").first
                await blik.click(force=True, timeout=5000)
                log.info(f"[{email}] Payment: BLIK selected")
            except:
                # Fallback: click first payment option
                await page.evaluate("""() => {
                    const radios = document.querySelectorAll('input[name="payment"]');
                    if (radios.length > 0) radios[0].click();
                }""")
                log.info(f"[{email}] Payment: first option (fallback)")

            await page.wait_for_timeout(2000)

            # Select delivery (Kurier Inpost Gabaryt C or first available)
            try:
                delivery = page.locator("text=Kurier Inpost").first
                await delivery.click(force=True, timeout=5000)
                log.info(f"[{email}] Delivery: Kurier Inpost")
            except:
                await page.evaluate("""() => {
                    const radios = document.querySelectorAll('input[name="delivery"]');
                    if (radios.length > 0) radios[0].click();
                }""")
                log.info(f"[{email}] Delivery: first option (fallback)")

            await page.wait_for_timeout(1000)

            # Check required checkboxes
            await page.evaluate("""() => {
                window.scrollTo(0, document.body.scrollHeight);
                const cbs = document.querySelectorAll('input[type="checkbox"]');
                for (const cb of cbs) {
                    const isRequired = cb.getAttribute('data-valid')?.includes('required');
                    if (isRequired && !cb.checked) cb.click();
                }
            }""")
            await page.wait_for_timeout(500)

            # Submit order
            log.info(f"[{email}] Submitting order... ({time.time()-t0:.2f}s)")
            order_submit = page.locator("button[name='finish']").first
            try:
                await order_submit.wait_for(state="visible", timeout=5000)
                await order_submit.click(force=True)
            except:
                # Fallback
                await page.evaluate("""() => {
                    const btn = document.querySelector('button[name="finish"]');
                    if (btn) btn.click();
                }""")

            # Wait for result
            await page.wait_for_timeout(5000)
            final_url = page.url
            total_time = time.time() - t0

            # Check success
            success = any(kw in final_url.lower() for kw in ["potwierdzenie", "thank", "tpay", "blik", "przelewy24"])
            if not success:
                content = await page.content()
                success = any(kw in content.lower() for kw in ["zamówienie zostało złożone", "dziękujemy"])

            if success:
                log.info(f"[{email}] ✅ ORDER PLACED in {total_time:.1f}s! URL: {final_url}")
                _mark_completed(product_id, email)
                await browser.close()
                return True
            else:
                log.error(f"[{email}] ❌ Order unclear ({total_time:.1f}s) URL: {final_url}")
                await page.screenshot(path=f"/tmp/jc_torpedo_{email.split('@')[0]}.png")
                await browser.close()
                return False

        except Exception as e:
            log.error(f"[{email}] Exception: {e} ({time.time()-t0:.1f}s)")
            try:
                await page.screenshot(path=f"/tmp/jc_torpedo_err_{email.split('@')[0]}.png")
            except:
                pass
            await browser.close()
            return False


def _mark_completed(product_id, email):
    data = {}
    if COMPLETED_FILE.exists():
        try:
            data = json.loads(COMPLETED_FILE.read_text())
        except:
            pass
    pid = str(product_id)
    if pid not in data:
        data[pid] = []
    if email not in data[pid]:
        data[pid].append(email)
    COMPLETED_FILE.write_text(json.dumps(data, indent=2))


# ============================================================
# DISCORD
# ============================================================

async def _send_discord(msg):
    try:
        if not WEBHOOK_FILE.exists():
            return
        wh = WEBHOOK_FILE.read_text().strip()
        if not wh:
            return
        async with aiohttp.ClientSession() as s:
            await s.post(wh, json={"content": msg})
    except:
        pass


# ============================================================
# FIRE (parallel all accounts)
# ============================================================

async def fire(product_id, product_url="", accounts_count=4):
    """Fire torpedo on all accounts in PARALLEL."""
    t0 = time.time()
    accounts = ACCOUNTS[:accounts_count]

    log.info(f"=== TORPEDO FIRE: product {product_id}, {len(accounts)} accounts ===")
    await _send_discord(f"🚀 **TORPEDO FIRE** product {product_id} — {len(accounts)} accounts")

    tasks = [torpedo_buy(acc, product_id, product_url) for acc in accounts]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    total_time = time.time() - t0
    ok = sum(1 for r in results if r is True)

    log.info(f"=== TORPEDO DONE: {ok}/{len(accounts)} in {total_time:.1f}s ===")

    status = "✅" if ok > 0 else "❌"
    await _send_discord(
        f"{status} **TORPEDO** product {product_id}\n"
        f"Success: {ok}/{len(accounts)} | Time: {total_time:.1f}s"
    )
    return ok


# ============================================================
# MAIN
# ============================================================

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="JC Torpedo v2 — hybrid instant buy")
    parser.add_argument("action", choices=["fire", "warmup"], help="fire=buy now, warmup=not needed (login inline)")
    parser.add_argument("--product-id", "-p", help="Product ID to buy")
    parser.add_argument("--url", "-u", default="", help="Product URL")
    parser.add_argument("--accounts", type=int, default=4, help="Number of accounts (1-4)")
    parser.add_argument("--test", action="store_true", help="Use test account (Marian Wasilewski)")
    args = parser.parse_args()

    if args.action == "warmup":
        log.info("Warmup not needed — torpedo v2 logs in inline (HTTP). Ready to fire.")
    elif args.action == "fire":
        if not args.product_id:
            print("ERROR: --product-id required for fire")
            sys.exit(1)
        if args.test:
            log.info("=== TEST MODE: Marian Wasilewski ===")
            ok = await torpedo_buy(TEST_ACCOUNT, args.product_id, args.url)
            sys.exit(0 if ok else 1)
        else:
            ok = await fire(args.product_id, args.url, args.accounts)
            sys.exit(0 if ok > 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
