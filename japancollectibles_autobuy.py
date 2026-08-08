#!/usr/bin/env python3
"""
JapanCollectibles.shop Auto-Buy Bot
Platform: Sky-Shop (AngularJS SPA)
Flow: Login -> ATC -> Cart -> Checkout (przelew + Kurier InPost C + zgody) -> Order
"""
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# Patchright for stealth
from patchright.async_api import async_playwright

BASE_DIR = Path("/opt/pokemon-monitor-v2")
COMPLETED_FILE = BASE_DIR / "japancollectibles_completed.json"
LOG_FILE = BASE_DIR / "japancollectibles_autobuy.log"
WEBHOOK_FILE = BASE_DIR / "discord_webhook_jc.txt"
SHOP_URL = "https://japancollectibles.shop"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [JC-BOT] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# 4 accounts (same as other bots)
ACCOUNTS = [
    {"email": "esemento@gmail.com", "password": "cR!9GW#x2wqJtGw", "name": "Tomasz Szczepaniak"},
    {"email": "blackmat36@gmail.com", "password": "v2@pvDGt#ZuN3ui", "name": "Natalia Szczepaniak"},
    {"email": "tjbtaniojuzbylo@gmail.com", "password": "P9XAfQE.SCwFq5i", "name": "Jagoda Kaczmarek"},
    {"email": "y24015411@gmail.com", "password": "huw!e.twdCmv9@B", "name": "Mirosława Szczepaniak"},
]


def load_completed():
    if COMPLETED_FILE.exists():
        return json.loads(COMPLETED_FILE.read_text())
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


async def send_discord(msg, embed=None):
    """Send Discord notification via webhook."""
    try:
        if not WEBHOOK_FILE.exists():
            log.warning("No webhook file, skip Discord notify")
            return
        webhook_url = WEBHOOK_FILE.read_text().strip()
        if not webhook_url:
            return
        import aiohttp
        payload = {"content": msg}
        if embed:
            payload["embeds"] = [embed]
        async with aiohttp.ClientSession() as session:
            await session.post(webhook_url, json=payload)
    except Exception as e:
        log.error(f"Discord send failed: {e}")


async def buy_product(account, product_url, product_id, qty=1, dry_run=False):
    """
    Full purchase flow for one account on one product.
    Returns True if order placed successfully.
    """
    email = account["email"]
    log.info(f"[{email}] Starting buy for product {product_id} (qty={qty}, dry_run={dry_run})")

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

            # Age gate - click confirm button
            try:
                age_btn = page.locator(".skyshop-alert-conditional-access button, .skyshop-alert-conditional-access a.btn")
                if await age_btn.count() > 0:
                    await age_btn.first.click(force=True)
                    log.info(f"[{email}] Age gate confirmed")
                    await page.wait_for_timeout(1000)
            except:
                pass
            # Cookie consent - accept all
            try:
                cc_btn = page.locator("#c-p-bn")
                if await cc_btn.count() > 0:
                    await cc_btn.first.click(force=True)
                    log.info(f"[{email}] Cookie consent accepted")
                    await page.wait_for_timeout(1000)
            except:
                pass
            # Force remove any remaining overlays
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.querySelector('.fixed-elements')?.remove();
            }""")
            log.info(f"[{email}] Overlays cleared")

            # === 1. LOGIN ===
            log.info(f"[{email}] Step 1: Login")
            await page.goto(f"{SHOP_URL}/login", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            # Remove overlays again (cookie consent reappears on new page)
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

            # Wait for redirect or page to load after login
            await page.wait_for_timeout(3000)
            # Verify login by checking for "Moje konto" or user menu
            content = await page.content()
            if "Moje konto" not in content and "Wyloguj" not in content:
                log.error(f"[{email}] Login FAILED - 'Moje konto' not found")
                return False
            log.info(f"[{email}] Login OK")

            # === 1.5. CLEAR CART ===
            log.info(f"[{email}] Clearing cart...")
            await page.goto(f"{SHOP_URL}/cart/", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            # Remove all items from cart via Angular
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.querySelector('.fixed-elements')?.remove();
            }""")
            # Click all delete buttons
            let_deleted = await page.evaluate("""() => {
                const delBtns = document.querySelectorAll('[data-click="deleteCartItem"], button[aria-label*="Usuń"], .icon-close_24, [data-ng-click*="delete"]');
                let count = 0;
                delBtns.forEach(btn => { btn.click(); count++; });
                return count;
            }""")
            if let_deleted > 0:
                log.info(f"[{email}] Deleted {let_deleted} items from cart")
                await page.wait_for_timeout(2000)
            else:
                log.info(f"[{email}] Cart already empty")

            # === 2. ADD TO CART ===
            log.info(f"[{email}] Step 2: ATC (product {product_id}, qty={qty})")
            for i in range(qty):
                await page.goto(product_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)

                # Dismiss cookie consent if it reappears
                await page.evaluate("""() => {
                    document.getElementById('cc--main')?.remove();
                    document.querySelector('.fixed-elements')?.remove();
                }""")

                # Wait for ATC button to be enabled (Angular hydration)
                try:
                    # On product page: click the main "Do koszyka" button (force to bypass overlays)
                    atc_btn = page.locator("button:has-text('Do koszyka'), button[aria-label*='Dodaj do koszyka']").first
                    await atc_btn.wait_for(state="visible", timeout=10000)
                    await atc_btn.click(force=True)
                    log.info(f"[{email}] ATC click {i+1}/{qty} OK")
                    await page.wait_for_timeout(2000)

                    # Dismiss "Produkt dodany" popup if present - click "Kontynuuj zakupy" or close
                    try:
                        realize_btn = page.locator("text=Realizuj zamówienie")
                        cont_btn = page.locator("text=Kontynuuj zakupy")
                        if await realize_btn.is_visible(timeout=3000):
                            # If last item, click "Realizuj zamówienie" to go to cart
                            if i == qty - 1:
                                await realize_btn.click()
                            else:
                                await cont_btn.click()
                            await page.wait_for_timeout(1000)
                    except:
                        pass

                except Exception as e:
                    log.error(f"[{email}] ATC failed at item {i+1}: {e}")
                    # If product unavailable, stop
                    if "disabled" in str(e).lower() or "timeout" in str(e).lower():
                        log.error(f"[{email}] Product likely unavailable, stopping")
                        return False

            # === 3. GO TO CART ===
            log.info(f"[{email}] Step 3: Cart -> Przejdź do kasy")
            await page.goto(f"{SHOP_URL}/cart/", wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)  # Wait for Angular to load cart data

            # Remove overlays
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.querySelector('.fixed-elements')?.remove();
            }""")

            # Wait for button to become enabled (Angular finishes loading)
            checkout_btn = page.locator("button[data-ng-click='order()']:not([disabled])")
            await checkout_btn.wait_for(state="visible", timeout=30000)
            await checkout_btn.click(force=True)

            # Wait for /order page to load
            await page.wait_for_url("**/order**", timeout=15000)
            await page.wait_for_timeout(3000)
            log.info(f"[{email}] Checkout page loaded: {page.url}")

            # === 4. SELECT PAYMENT: "BLIK" ===
            log.info(f"[{email}] Step 4: Select payment - BLIK")
            await page.wait_for_timeout(5000)  # Wait for Angular to render checkout

            # Remove overlays
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.querySelector('.fixed-elements')?.remove();
            }""")

            # Wait for payment options to render (not {{:name:}} templates)
            for _ in range(10):
                has_payments = await page.evaluate("() => document.body.innerText.includes('BLIK')")
                if has_payments:
                    break
                await page.wait_for_timeout(2000)

            # Click "BLIK" using Playwright click (triggers Angular properly)
            payment_clicked = False
            try:
                payment_el = page.locator("text=BLIK").first
                await payment_el.wait_for(state="visible", timeout=10000)
                await payment_el.click(force=True)
                payment_clicked = True
                log.info(f"[{email}] Payment clicked: BLIK")
            except Exception as e:
                log.error(f"[{email}] Payment click failed: {e}")

            if not payment_clicked:
                await page.screenshot(path="/tmp/jc_payment_fail.png")
                log.error(f"[{email}] Payment NOT FOUND")
                return False

            await page.wait_for_timeout(5000)  # Wait for delivery to appear after payment selection

            # === 5. SELECT DELIVERY: "Kurier Inpost - Gabaryt C" ===
            log.info(f"[{email}] Step 5: Select delivery - Kurier Inpost Gabaryt C")
            
            # Wait for delivery options to render
            for _ in range(10):
                has_delivery = await page.evaluate("() => document.body.innerText.includes('Kurier Inpost')")
                if has_delivery:
                    break
                await page.wait_for_timeout(2000)

            # Click using Playwright - the row element, not hidden label
            delivery_clicked = False
            try:
                # The visible text is in the row, label is hidden. Click the row containing "Kurier Inpost" + "Gabaryt C"
                # Try visible element containing this text
                delivery_el = page.locator("text=Kurier Inpost - Gabaryt C >> visible=true")
                if await delivery_el.count() == 0:
                    # Click the row/parent of radio for-id 6512b
                    delivery_el = page.locator("input#param-delivery-6512b")
                    if await delivery_el.count() > 0:
                        await delivery_el.evaluate("el => el.closest('tr, div, .shipment-row')?.click() || el.click()")
                        delivery_clicked = True
                        log.info(f"[{email}] Delivery clicked via radio parent")
                    else:
                        # Find by partial text in visible elements
                        delivery_el = page.locator("td:has-text('Kurier Inpost'), div:has-text('Kurier Inpost')").filter(has_text="Gabaryt C")
                        if await delivery_el.count() > 0:
                            await delivery_el.first.click(force=True)
                            delivery_clicked = True
                            log.info(f"[{email}] Delivery clicked via td/div")
                else:
                    await delivery_el.first.click(force=True)
                    delivery_clicked = True
                    log.info(f"[{email}] Delivery clicked: Kurier Inpost - Gabaryt C")
            except Exception as e:
                log.warning(f"[{email}] Delivery PW click failed: {e}")

            # Fallback: JS click on the row containing 6512b or "Gabaryt C"
            if not delivery_clicked:
                result = await page.evaluate("""() => {
                    // Find radio with id containing 6512b and click its parent row
                    const radio = document.getElementById('param-delivery-6512b');
                    if (radio) {
                        const row = radio.closest('tr') || radio.closest('div') || radio.parentElement;
                        if (row) { row.click(); return 'row_clicked'; }
                        radio.click();
                        return 'radio_clicked';
                    }
                    // Fallback: find any row with Gabaryt C text
                    const rows = document.querySelectorAll('.core_setOrderShipment, tr');
                    for (const row of rows) {
                        if (row.textContent.includes('Gabaryt C') && row.textContent.toLowerCase().includes('kurier')) {
                            row.click();
                            return 'text_row_clicked: ' + row.textContent.trim().substring(0, 50);
                        }
                    }
                    return 'NOT_FOUND';
                }""")
                log.info(f"[{email}] Delivery JS fallback: {result}")
                if "clicked" in str(result):
                    delivery_clicked = True

            if not delivery_clicked:
                await page.screenshot(path="/tmp/jc_delivery_fail.png")
                log.error(f"[{email}] Delivery NOT FOUND")
                return False

            await page.wait_for_timeout(2000)

            # === 6. CHECKBOXES (zgody z gwiazdką) ===
            log.info(f"[{email}] Step 6: Check consent checkboxes")
            # Scroll to bottom to make checkboxes visible
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)
            # Check all required checkboxes using JS (force - they may be outside viewport)
            checked_count = await page.evaluate("""() => {
                let count = 0;
                const cbs = document.querySelectorAll('input[type="checkbox"]');
                for (const cb of cbs) {
                    const isRequired = cb.getAttribute('data-valid')?.includes('required');
                    if (isRequired && !cb.checked) {
                        cb.click();
                        count++;
                    }
                }
                return count;
            }""")
            log.info(f"[{email}] Checkboxes checked ({checked_count} clicked)")
            await page.wait_for_timeout(1000)

            # === 7. SUBMIT ORDER ===
            if dry_run:
                log.info(f"[{email}] DRY RUN - NOT clicking 'Zamawiam i płacę'")
                await page.screenshot(path=f"/tmp/jc_dryrun_{email.split('@')[0]}.png")
                # Dump page state for debug
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
                log.info(f"[{email}] Page state: {json.dumps(state)}")
                return True

            log.info(f"[{email}] Step 7: Click 'Zamawiam i płacę'")
            order_btn = page.locator("button[name='finish']").first
            await order_btn.wait_for(state="visible", timeout=10000)
            await order_btn.click(force=True)

            # Wait for order confirmation
            await page.wait_for_timeout(5000)
            final_url = page.url
            final_content = await page.content()
            log.info(f"[{email}] After order click, URL: {final_url}")

            if "potwierdzenie" in final_url or "thank" in final_url or "zamówienie" in final_content.lower() or "blik.com" in final_url or "tpay" in final_url:
                log.info(f"[{email}] ORDER PLACED SUCCESSFULLY! (redirect: {final_url})")
                mark_completed(product_id, email)
                await send_discord(f"✅ **{account['name']}** - zamówienie złożone!\nProdukt: {product_url}\n💳 Zapłać BLIK: {final_url}")
                return True
            elif "order" in final_url and "error" not in final_content.lower():
                # Maybe still on order page - check for errors
                errors = await page.evaluate("""() => {
                    const errs = document.querySelectorAll('.error, .alert-danger, .text-danger, [class*="error"]');
                    return [...errs].map(e => e.textContent.trim()).filter(t => t.length > 0);
                }""")
                if errors:
                    log.error(f"[{email}] Order errors: {errors}")
                    return False
                # No errors but still on page - might have worked (redirect to bank)
                log.info(f"[{email}] No errors found, URL: {final_url} - likely redirect to payment page")
                mark_completed(product_id, email)
                await send_discord(f"✅ **{account['name']}** - zamówienie złożone!\nProdukt: {product_url}\nPłatność: BLIK - zapłać w apce!")
                return True
            else:
                log.error(f"[{email}] Order unclear, URL: {final_url}")
                await page.screenshot(path=f"/tmp/jc_order_unclear_{email.split('@')[0]}.png")
                return False

        except Exception as e:
            log.error(f"[{email}] Exception: {e}")
            try:
                await page.screenshot(path=f"/tmp/jc_error_{email.split('@')[0]}.png")
            except:
                pass
            return False
        finally:
            # Logout before closing
            try:
                await page.goto(f"{SHOP_URL}/logout", wait_until="domcontentloaded")
                await page.wait_for_timeout(1000)
                log.info(f"[{email}] Logged out")
            except:
                pass
            await browser.close()


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="JapanCollectibles Auto-Buy Bot")
    parser.add_argument("product_urls", nargs="+", help="Product URLs or IDs to buy")
    parser.add_argument("--test", action="store_true", help="Dry run (don't submit order)")
    parser.add_argument("--accounts", type=int, default=4, help="Number of accounts to use (1-4)")
    parser.add_argument("--qty", type=int, default=1, help="Quantity per product per account")
    args = parser.parse_args()

    accounts_to_use = ACCOUNTS[:args.accounts]
    product_urls = args.product_urls

    log.info(f"=== JC Bot Start: {len(product_urls)} products, {len(accounts_to_use)} accounts, qty={args.qty}, dry_run={args.test} ===")

    results = []
    for product_input in product_urls:
        # Accept URL or product ID
        if product_input.startswith("http"):
            product_url = product_input
            # Extract product ID from URL (format: ...-p{ID})
            import re
            match = re.search(r'-p(\d+)$', product_url.split('?')[0])
            product_id = match.group(1) if match else product_input
        else:
            product_id = product_input
            product_url = f"{SHOP_URL}/-p{product_id}"  # Will redirect

        for account in accounts_to_use:
            if is_completed(product_id, account["email"]):
                log.info(f"[{account['email']}] Product {product_id} already completed, skip")
                continue

            success = await buy_product(account, product_url, product_id, qty=args.qty, dry_run=args.test)
            results.append((account["email"], product_id, success))

            if success:
                log.info(f"[{account['email']}] Product {product_id}: SUCCESS")
            else:
                log.warning(f"[{account['email']}] Product {product_id}: FAILED")

            # Small delay between accounts
            await asyncio.sleep(2)

    # Summary
    ok = sum(1 for _, _, s in results if s)
    total = len(results)
    log.info(f"=== DONE: {ok}/{total} successful ===")

    # Discord notify
    if ok > 0 and not args.test:
        await send_discord(f"🛒 **JapanCollectibles AutoBuy** - {ok}/{total} zamówień złożonych!\nZapłać przelewem: Konto → Historia zamówień → Zapłać")
    elif ok == 0 and total > 0 and not args.test:
        await send_discord(f"❌ **JapanCollectibles AutoBuy** - 0/{total} zamówień (wszystkie failed)")

    return ok > 0


if __name__ == "__main__":
    asyncio.run(main())
