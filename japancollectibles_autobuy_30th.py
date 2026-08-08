#!/usr/bin/env python3
"""
JapanCollectibles.shop Auto-Buy Bot - 30th Anniversary BATCH
Platform: Sky-Shop (AngularJS SPA)
Flow per account: Login -> Clear Cart -> ATC product1 -> ATC product2 -> ... -> Cart -> Checkout -> Order

DIFFERENCE from japancollectibles_autobuy.py:
- Adds MULTIPLE products to ONE cart, then checks out ONCE per account
- Separate completed file (japancollectibles_30th_completed.json)
- Triggered by japancollectibles_30th_trigger.py

Usage:
    python3 japancollectibles_autobuy_30th.py --accounts 4 --qty 1 URL1 URL2 URL3
    python3 japancollectibles_autobuy_30th.py --test --accounts 1 --qty 1 URL1
"""
import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

from patchright.async_api import async_playwright

BASE_DIR = Path("/opt/pokemon-monitor-v2")
COMPLETED_FILE = BASE_DIR / "japancollectibles_30th_completed.json"
LOG_FILE = BASE_DIR / "japancollectibles_30th_autobuy.log"
WEBHOOK_FILE = BASE_DIR / "discord_webhook_jc.txt"
SHOP_URL = "https://japancollectibles.shop"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [JC-30TH] %(message)s",
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


def load_completed():
    if COMPLETED_FILE.exists():
        try:
            return json.loads(COMPLETED_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_completed(data):
    COMPLETED_FILE.write_text(json.dumps(data, indent=2))


def is_completed(product_id, account_email):
    data = load_completed()
    return account_email in data.get(str(product_id), [])


def mark_completed(product_id, account_email):
    data = load_completed()
    pid = str(product_id)
    if pid not in data:
        data[pid] = []
    if account_email not in data[pid]:
        data[pid].append(account_email)
    save_completed(data)


def extract_pid(url_or_id):
    """Extract product ID from URL or return as-is."""
    if url_or_id.startswith("http"):
        match = re.search(r'-p(\d+)', url_or_id.split('?')[0])
        return match.group(1) if match else url_or_id
    return url_or_id


async def send_discord(msg):
    """Send Discord notification via webhook."""
    try:
        if not WEBHOOK_FILE.exists():
            return
        webhook_url = WEBHOOK_FILE.read_text().strip()
        if not webhook_url:
            return
        import aiohttp
        async with aiohttp.ClientSession() as session:
            await session.post(webhook_url, json={"content": msg})
    except Exception as e:
        log.error(f"Discord send failed: {e}")


async def buy_batch(account, product_urls, qty=1, dry_run=False):
    """
    Buy ALL products in ONE cart for one account.
    Returns: (success: bool, bought_pids: list)
    """
    email = account["email"]
    bought_pids = []

    log.info(f"[{email}] BATCH BUY: {len(product_urls)} products, qty={qty}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        try:
            # === 0. DISMISS OVERLAYS (age gate + cookies) ===
            log.info(f"[{email}] Step 0: Dismiss overlays")
            await page.goto(SHOP_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # Age gate
            try:
                age_btn = page.locator(".skyshop-alert-conditional-access button, .skyshop-alert-conditional-access a.btn")
                if await age_btn.count() > 0:
                    await age_btn.first.click(force=True)
                    log.info(f"[{email}] Age gate confirmed")
                    await page.wait_for_timeout(1000)
            except:
                pass
            # Cookie consent
            try:
                cc_btn = page.locator("#c-p-bn")
                if await cc_btn.count() > 0:
                    await cc_btn.first.click(force=True)
                    log.info(f"[{email}] Cookie consent accepted")
                    await page.wait_for_timeout(1000)
            except:
                pass
            # Force remove overlays
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.querySelector('.fixed-elements')?.remove();
            }""")

            # === 1. LOGIN ===
            log.info(f"[{email}] Step 1: Login")
            await page.goto(f"{SHOP_URL}/login", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.getElementById('cm')?.remove();
                document.getElementById('c-inr-i')?.remove();
                document.getElementById('cm-ov')?.remove();
                document.querySelector('.fixed-elements')?.remove();
            }""")
            await page.wait_for_selector("input#email", timeout=15000)

            await page.fill("input#email", email)
            await page.fill("input[name='password']", account["password"])
            await page.click("button[name='submit']", force=True)
            await page.wait_for_timeout(3000)

            content = await page.content()
            if "Moje konto" not in content and "Wyloguj" not in content:
                log.error(f"[{email}] Login FAILED")
                return False, []
            log.info(f"[{email}] Login OK")

            # === 1.5. CLEAR CART ===
            log.info(f"[{email}] Clearing cart...")
            await page.goto(f"{SHOP_URL}/cart/", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.querySelector('.fixed-elements')?.remove();
            }""")
            let_deleted = await page.evaluate("""() => {
                const delBtns = document.querySelectorAll('[data-click="deleteCartItem"], button[aria-label*="Usuń"], .icon-close_24, [data-ng-click*="delete"]');
                let count = 0;
                delBtns.forEach(btn => { btn.click(); count++; });
                return count;
            }""")
            if let_deleted > 0:
                log.info(f"[{email}] Deleted {let_deleted} items from cart")
                await page.wait_for_timeout(2000)

            # === 2. ADD ALL PRODUCTS TO CART ===
            log.info(f"[{email}] Step 2: Adding {len(product_urls)} products to cart")
            for idx, product_url in enumerate(product_urls):
                pid = extract_pid(product_url)
                log.info(f"[{email}] ATC [{idx+1}/{len(product_urls)}] pid={pid}")

                for i in range(qty):
                    await page.goto(product_url, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)

                    # Dismiss overlays
                    await page.evaluate("""() => {
                        document.getElementById('cc--main')?.remove();
                        document.querySelector('.fixed-elements')?.remove();
                    }""")

                    # Click ATC
                    try:
                        atc_btn = page.locator("button:has-text('Do koszyka'), button[aria-label*='Dodaj do koszyka']").first
                        await atc_btn.wait_for(state="visible", timeout=10000)
                        await atc_btn.click(force=True)
                        log.info(f"[{email}] ATC click {i+1}/{qty} for {pid} OK")
                        await page.wait_for_timeout(2000)

                        # Dismiss popup - always "Kontynuuj zakupy" (we'll checkout at the end)
                        try:
                            cont_btn = page.locator("text=Kontynuuj zakupy")
                            if await cont_btn.is_visible(timeout=3000):
                                await cont_btn.click()
                                await page.wait_for_timeout(1000)
                        except:
                            pass

                    except Exception as e:
                        log.error(f"[{email}] ATC failed for {pid}: {e}")
                        break

                bought_pids.append(pid)

            if not bought_pids:
                log.error(f"[{email}] No products added to cart!")
                return False, []

            log.info(f"[{email}] All {len(bought_pids)} products added to cart")

            # === 3. GO TO CART -> CHECKOUT ===
            log.info(f"[{email}] Step 3: Cart -> Przejdź do kasy")
            await page.goto(f"{SHOP_URL}/cart/", wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.querySelector('.fixed-elements')?.remove();
            }""")

            checkout_btn = page.locator("button[data-ng-click='order()']:not([disabled])")
            await checkout_btn.wait_for(state="visible", timeout=30000)
            await checkout_btn.click(force=True)

            await page.wait_for_url("**/order**", timeout=15000)
            await page.wait_for_timeout(3000)
            log.info(f"[{email}] Checkout page loaded: {page.url}")

            # === 4. SELECT PAYMENT: BLIK ===
            log.info(f"[{email}] Step 4: Select payment - BLIK")
            await page.wait_for_timeout(5000)

            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.querySelector('.fixed-elements')?.remove();
            }""")

            for _ in range(10):
                has_payments = await page.evaluate("() => document.body.innerText.includes('BLIK')")
                if has_payments:
                    break
                await page.wait_for_timeout(2000)

            payment_clicked = False
            try:
                payment_el = page.locator("text=BLIK").first
                await payment_el.wait_for(state="visible", timeout=10000)
                await payment_el.click(force=True)
                payment_clicked = True
                log.info(f"[{email}] Payment: BLIK selected")
            except Exception as e:
                log.error(f"[{email}] Payment click failed: {e}")

            if not payment_clicked:
                await page.screenshot(path=f"/tmp/jc30_payment_fail_{email.split('@')[0]}.png")
                return False, []

            await page.wait_for_timeout(5000)

            # === 5. SELECT DELIVERY: Kurier Inpost - Gabaryt C ===
            log.info(f"[{email}] Step 5: Select delivery - Kurier Inpost Gabaryt C")

            for _ in range(10):
                has_delivery = await page.evaluate("() => document.body.innerText.includes('Kurier Inpost')")
                if has_delivery:
                    break
                await page.wait_for_timeout(2000)

            delivery_clicked = False
            try:
                delivery_el = page.locator("text=Kurier Inpost - Gabaryt C >> visible=true")
                if await delivery_el.count() == 0:
                    delivery_el = page.locator("input#param-delivery-6512b")
                    if await delivery_el.count() > 0:
                        await delivery_el.evaluate("el => el.closest('tr, div, .shipment-row')?.click() || el.click()")
                        delivery_clicked = True
                    else:
                        delivery_el = page.locator("td:has-text('Kurier Inpost'), div:has-text('Kurier Inpost')").filter(has_text="Gabaryt C")
                        if await delivery_el.count() > 0:
                            await delivery_el.first.click(force=True)
                            delivery_clicked = True
                else:
                    await delivery_el.first.click(force=True)
                    delivery_clicked = True
            except Exception as e:
                log.warning(f"[{email}] Delivery PW click failed: {e}")

            if not delivery_clicked:
                result = await page.evaluate("""() => {
                    const radio = document.getElementById('param-delivery-6512b');
                    if (radio) {
                        const row = radio.closest('tr') || radio.closest('div') || radio.parentElement;
                        if (row) { row.click(); return 'row_clicked'; }
                        radio.click(); return 'radio_clicked';
                    }
                    const rows = document.querySelectorAll('.core_setOrderShipment, tr');
                    for (const row of rows) {
                        if (row.textContent.includes('Gabaryt C') && row.textContent.toLowerCase().includes('kurier')) {
                            row.click(); return 'text_row_clicked';
                        }
                    }
                    return 'NOT_FOUND';
                }""")
                log.info(f"[{email}] Delivery JS fallback: {result}")
                if "clicked" in str(result):
                    delivery_clicked = True

            if not delivery_clicked:
                await page.screenshot(path=f"/tmp/jc30_delivery_fail_{email.split('@')[0]}.png")
                return False, []

            log.info(f"[{email}] Delivery selected OK")
            await page.wait_for_timeout(2000)

            # === 6. CHECKBOXES ===
            log.info(f"[{email}] Step 6: Checkboxes")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)
            checked_count = await page.evaluate("""() => {
                let count = 0;
                const cbs = document.querySelectorAll('input[type="checkbox"]');
                for (const cb of cbs) {
                    const isRequired = cb.getAttribute('data-valid')?.includes('required');
                    if (isRequired && !cb.checked) { cb.click(); count++; }
                }
                return count;
            }""")
            log.info(f"[{email}] Checkboxes: {checked_count} clicked")
            await page.wait_for_timeout(1000)

            # === 7. SUBMIT ORDER ===
            if dry_run:
                log.info(f"[{email}] DRY RUN - NOT submitting order")
                state = await page.evaluate("""() => {
                    const radios = [...document.querySelectorAll('input[type="radio"]:checked')];
                    const cbs = [...document.querySelectorAll('input[type="checkbox"]:checked')];
                    const btn = document.querySelector('button[name="finish"]');
                    return {
                        payment_radio: radios.map(r => r.name + '=' + r.value),
                        checkboxes: cbs.map(c => c.name || c.id),
                        order_btn: btn ? {text: btn.textContent.trim(), disabled: btn.disabled} : 'NOT FOUND'
                    };
                }""")
                log.info(f"[{email}] State: {json.dumps(state)}")
                return True, []

            log.info(f"[{email}] Step 7: Zamawiam i płacę")
            order_btn = page.locator("button[name='finish']").first
            await order_btn.wait_for(state="visible", timeout=10000)
            await order_btn.click(force=True)
            await page.wait_for_timeout(8000)

            final_url = page.url
            log.info(f"[{email}] After order, URL: {final_url}")

            if any(x in final_url for x in ["blik.com", "tpay.com", "przelewy24", "payu.com", "platnosci"]):
                log.info(f"[{email}] ORDER SUCCESS! Payment redirect: {final_url}")
                for pid in bought_pids:
                    mark_completed(pid, email)
                await send_discord(f"✅ **{account['name']}** - zamówienie ({len(bought_pids)} produktów)!\n💳 Zapłać: {final_url}")
                return True, bought_pids
            elif "order" in final_url:
                errors = await page.evaluate("""() => {
                    const errs = document.querySelectorAll('.error, .alert-danger, .text-danger');
                    return [...errs].map(e => e.textContent.trim()).filter(t => t.length > 0);
                }""")
                if not errors:
                    log.info(f"[{email}] Likely success (no errors)")
                    for pid in bought_pids:
                        mark_completed(pid, email)
                    await send_discord(f"✅ **{account['name']}** - zamówienie ({len(bought_pids)} produktów)!\nURL: {final_url}")
                    return True, bought_pids
                else:
                    log.error(f"[{email}] Order errors: {errors}")
                    return False, []
            else:
                log.error(f"[{email}] Order unclear: {final_url}")
                await page.screenshot(path=f"/tmp/jc30_unclear_{email.split('@')[0]}.png")
                return False, []

        except Exception as e:
            log.error(f"[{email}] Exception: {e}")
            try:
                await page.screenshot(path=f"/tmp/jc30_error_{email.split('@')[0]}.png")
            except:
                pass
            return False, []
        finally:
            try:
                await page.goto(f"{SHOP_URL}/logout", wait_until="domcontentloaded")
                await page.wait_for_timeout(1000)
                log.info(f"[{email}] Logged out")
            except:
                pass
            await browser.close()


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="JC 30th Anniversary Batch Auto-Buy")
    parser.add_argument("product_urls", nargs="+", help="Product URLs to buy")
    parser.add_argument("--test", action="store_true", help="Dry run")
    parser.add_argument("--accounts", type=int, default=4, help="Number of accounts (1-4)")
    parser.add_argument("--qty", type=int, default=1, help="Quantity per product")
    args = parser.parse_args()

    accounts_to_use = ACCOUNTS[:args.accounts]
    product_urls = args.product_urls

    log.info(f"{'='*60}")
    log.info(f"JC 30TH BATCH | {len(product_urls)} products | {len(accounts_to_use)} accounts | qty={args.qty} | dry_run={args.test}")
    log.info(f"Products: {product_urls}")
    log.info(f"{'='*60}")

    results = []
    for account in accounts_to_use:
        # Filter URLs - skip already completed for this account
        urls_to_buy = []
        for url in product_urls:
            pid = extract_pid(url)
            if not is_completed(pid, account["email"]):
                urls_to_buy.append(url)
            else:
                log.info(f"[{account['email']}] {pid} already completed, skip")

        if not urls_to_buy:
            log.info(f"[{account['email']}] All completed, skip")
            results.append((account["name"], True, []))
            continue

        success, bought = await buy_batch(account, urls_to_buy, qty=args.qty, dry_run=args.test)
        results.append((account["name"], success, bought))

        if success:
            log.info(f"[{account['email']}] BATCH OK: {len(bought)} products")
        else:
            log.warning(f"[{account['email']}] BATCH FAILED")

        await asyncio.sleep(3)

    # Summary
    ok = sum(1 for _, s, _ in results if s)
    total = len(results)
    log.info(f"\n{'='*60}")
    log.info(f"SUMMARY: {ok}/{total} accounts OK")
    for name, success, bought in results:
        log.info(f"  {'OK' if success else 'FAIL'} {name}: {len(bought)} products")
    log.info(f"{'='*60}")

    if not args.test:
        lines = [f"  {'✅' if s else '❌'} {n}: {len(b)} prod" for n, s, b in results]
        await send_discord(f"🛒 **JC 30th Batch** - {ok}/{total} kont\n" + "\n".join(lines))

    return ok > 0


if __name__ == "__main__":
    asyncio.run(main())
