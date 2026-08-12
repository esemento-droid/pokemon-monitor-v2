#!/usr/bin/env python3
"""
Kartexpol Auto-Buy Bot
Platform: Shoper (kartexpol.pl)
Method: Patchright headless=False (Shoper blocks aiohttp login)
Flow: Login → Clear cart → ATC → Basket → ZAMAWIAM →
      Select paczkomat + checkboxes → PODSUMOWANIE → POTWIERDZAM ZAKUP → Przelewy24
Accounts: 4 production + 1 test
Requires: DISPLAY=:99, Xvfb running
"""

import asyncio
import sys
import os
import json
import logging
import re
import time
import argparse
from pathlib import Path
from patchright.async_api import async_playwright
from bot_utils import wait_for_verification

# === CONFIG ===
BASE_URL = "https://www.kartexpol.pl"
SHOP_NAME = "kartexpol"
BOT_DIR = Path(__file__).parent
COMPLETED_FILE = BOT_DIR / "kartexpol_completed.json"
LOG_FILE = BOT_DIR / "kartexpol_autobuy.log"
WEBHOOK_FILE = BOT_DIR / "discord_webhook_kartexpol.txt"
PROXY = "http://127.0.0.1:8888"  # LEGACY fallback
import random
from bot_engine import BotEngine
_engine = BotEngine(shop="kartexpol", webhook_file=str(WEBHOOK_FILE))

ACCOUNTS = [
    {"email": "esemento@gmail.com", "password": "cR!9GW#x2wqJtGw", "name": "Tomasz Szczepaniak"},
    {"email": "blackmat36@gmail.com", "password": "v2@pvDGt#ZuN3ui", "name": "Natalia Szczepaniak"},
    {"email": "tjbtaniojuzbylo@gmail.com", "password": "P9XAfQE.SCwFq5i", "name": "Jagoda Kaczmarek"},
    {"email": "y24015411@gmail.com", "password": "huw!e.twdCmv9@B", "name": "Miroslawa Szczepaniak"},
]

TEST_ACCOUNT = {"email": "t11008543@gmail.com", "password": "mt!cSsphud4Zhnz", "name": "Marian Wasilewski"}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode="a"),
    ]
)
log = logging.getLogger("kartexpol_autobuy")


# === COMPLETED TRACKER ===

def load_completed():
    """Load completed purchases from JSON file. Return {} if missing or malformed."""
    try:
        if COMPLETED_FILE.exists():
            return json.loads(COMPLETED_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"Failed to load completed file: {e}")
    return {}


def save_completed(data):
    """Write completed dict to JSON file with indent=2."""
    COMPLETED_FILE.write_text(json.dumps(data, indent=2))


def is_completed(product_id, email):
    """Check if email has already completed purchase for product_id."""
    completed = load_completed()
    return email in completed.get(product_id, [])


def mark_completed(product_id, email):
    """Add email to completed[product_id] list and save."""
    completed = load_completed()
    if product_id not in completed:
        completed[product_id] = []
    if email not in completed[product_id]:
        completed[product_id].append(email)
    save_completed(completed)


# === DISCORD NOTIFICATIONS ===

async def send_discord(message):
    """Send Discord notification via webhook."""
    try:
        if not WEBHOOK_FILE.exists():
            log.warning("No Discord webhook file")
            return
        wh_url = WEBHOOK_FILE.read_text().strip()
        if not wh_url:
            return
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(wh_url, json={"content": message}, timeout=aiohttp.ClientTimeout(total=10))
    except Exception as e:
        log.warning(f"Discord send failed: {e}")


# === BROWSER AUTOMATION ===

async def dismiss_overlay(page):
    """Remove cookie consent overlays, modals, and restore pointer-events."""
    await page.evaluate("""
        document.querySelectorAll('.consents, .consents__mask, [class*=consent], .cookie-bar, h-portal-target[name="modals"], .consents-modal__footer, .modal__footer').forEach(el => el.remove());
        document.body.style.pointerEvents = 'auto';
        document.body.style.overflow = 'auto';
    """)


async def login(page, email, password):
    """
    Login to kartexpol.pl via JS form injection + button click.
    Returns True if "wyloguj" detected in page after submission.
    Retries up to 3 times with 3-second waits between attempts.
    """
    for attempt in range(3):
        try:
            await page.goto(f"{BASE_URL}/pl/login", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # Remove overlays — try clicking consent button first, then JS removal
            try:
                consent = page.locator('.consents__btn')
                if await consent.count() > 0:
                    await consent.first.click(timeout=3000)
                    await asyncio.sleep(1)
            except Exception:
                pass
            await dismiss_overlay(page)
            await asyncio.sleep(0.5)

            # Fill form via JS with input+change events
            escaped_email = email.replace("'", "\\'")
            escaped_pass = password.replace("\\", "\\\\").replace("'", "\\'")
            await page.evaluate(f"""() => {{
                const mailEl = document.querySelector('input[name="email"]') || document.querySelector('#mail_input_long') || document.querySelector('input[name="mail"]');
                const passEl = document.querySelector('input[name="password"]') || document.querySelector('#pass_input_long') || document.querySelector('input[name="pass"]');
                if (mailEl) {{
                    mailEl.focus();
                    mailEl.value = '{escaped_email}';
                    mailEl.dispatchEvent(new Event('input', {{bubbles:true}}));
                    mailEl.dispatchEvent(new Event('change', {{bubbles:true}}));
                }}
                if (passEl) {{
                    passEl.focus();
                    passEl.value = '{escaped_pass}';
                    passEl.dispatchEvent(new Event('input', {{bubbles:true}}));
                    passEl.dispatchEvent(new Event('change', {{bubbles:true}}));
                }}
            }}""")
            await asyncio.sleep(1)

            # Click "Zaloguj sie" button (NOT form.submit - that doesn't work on this Shoper version)
            await page.evaluate("""() => {
                const btn = Array.from(document.querySelectorAll('button[type="submit"]')).find(b => b.innerText.includes('Zaloguj'));
                if (btn) btn.click();
                else {
                    const form = document.querySelector('form[action*="/pl/login"]');
                    if (form) form.submit();
                }
            }""")
            await asyncio.sleep(5)

            # Check for successful login — "wyloguj" link present
            content = await page.content()
            if "wyloguj" in content.lower() or "Wyloguj" in content:
                return True

            log.warning(f"Login attempt {attempt+1} failed for {email}, url={page.url}")
        except Exception as e:
            log.warning(f"Login attempt {attempt+1} error for {email}: {e}")

        # Wait 3 seconds before retry
        if attempt < 2:
            await asyncio.sleep(3)

    return False


async def clear_cart(page):
    """
    Clear cart via popup: click cart icon → "Wyczyść" → "Usuń wszystkie produkty".
    If cart is already empty, does nothing.
    """
    # Navigate to main page to access cart icon
    await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(2)
    await dismiss_overlay(page)

    # Check if cart has items (look at cart count in header)
    cart_empty = await page.evaluate("""() => {
        const cartText = document.body.innerText;
        // Look for "0,00" in cart area or "koszyk jest pusty"
        const cartEl = document.querySelector('[class*="cart"] [class*="price"], [class*="basket"] [class*="total"]');
        if (cartEl && cartEl.innerText.includes('0,00')) return true;
        if (cartText.includes('Twój koszyk jest pusty')) return true;
        return false;
    }""")
    if cart_empty:
        return  # Already empty

    # Click cart icon to open popup
    try:
        cart_icon = page.locator('[class*="cart"], [class*="basket"], a[href*="basket"]').first
        await cart_icon.click(force=True, timeout=5000)
    except Exception:
        await page.evaluate("""() => {
            const cart = document.querySelector('a[href*="basket"], [class*="cart-icon"], [class*="basket"]');
            if (cart) cart.click();
        }""")
    await asyncio.sleep(2)

    # Click "Wyczyść" button in cart popup
    try:
        clear_btn = page.locator('text=Wyczyść').first
        await clear_btn.click(force=True, timeout=5000)
        await asyncio.sleep(2)
    except Exception:
        await page.evaluate("""() => {
            const btn = Array.from(document.querySelectorAll('button, a, span')).find(el => el.innerText.trim() === 'Wyczyść');
            if (btn) btn.click();
        }""")
        await asyncio.sleep(2)

    # Click "Usuń wszystkie produkty" in confirmation modal
    try:
        remove_btn = page.locator('text=Usuń wszystkie produkty').first
        await remove_btn.click(force=True, timeout=5000)
        await asyncio.sleep(2)
    except Exception:
        await page.evaluate("""() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Usuń wszystkie'));
            if (btn) btn.click();
        }""")
        await asyncio.sleep(2)

    # Verify cart is empty
    await asyncio.sleep(1)
    is_empty = await page.evaluate("""() => {
        return document.body.innerText.includes('koszyk jest pusty') || 
               document.body.innerText.includes('0,00');
    }""")
    if not is_empty:
        log.warning("Cart may not be fully cleared")


async def add_to_cart(page, product_url):
    """
    Navigate to product page and click .addtobasket via JS.
    After ATC, a popup appears with "Dostawa i płatność" button — we dismiss it
    and continue adding more products. The popup is handled later at checkout time.
    Returns True on success, False if button not found/disabled.
    """
    try:
        await page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        log.warning(f"Failed to load product page {product_url}: {e}")
        return False
    await asyncio.sleep(2)
    await dismiss_overlay(page)

    # Click ATC button via JS
    clicked = await page.evaluate("""
        () => {
            const btn = document.querySelector('.addtobasket') ||
                        document.querySelector('button.addtobasket') ||
                        document.querySelector('[class*="addtobasket"]') ||
                        document.querySelector('form[action*="basket"] button[type="submit"]');
            if (btn && !btn.disabled) {
                btn.click();
                return true;
            }
            return false;
        }
    """)

    if not clicked:
        # Fallback: try PW locator with force
        try:
            atc = page.locator('.addtobasket, button:has-text("Do koszyka")')
            if await atc.count() > 0:
                await atc.first.click(force=True, timeout=5000)
                clicked = True
        except Exception as e:
            log.warning(f"ATC fallback click failed for {product_url}: {e}")

    if not clicked:
        log.warning(f"ATC button not found or disabled for {product_url}")
        return False

    # Wait for cart popup to appear
    await asyncio.sleep(3)

    # Dismiss the cart popup by clicking outside or closing it
    # (We don't click "Dostawa i płatność" here — we'll navigate to checkout after all products are added)
    await page.evaluate("""
        () => {
            // Try to close the popup by clicking X/close button or clicking overlay
            const closeBtn = document.querySelector('.popup-close, .close, [class*="close"], .fancybox-close');
            if (closeBtn) { closeBtn.click(); return; }
            // Try clicking "Zobacz produkty w koszyku" or just dismiss overlay
            const overlay = document.querySelector('.fancybox-overlay, .popup-overlay, [class*="overlay"]');
            if (overlay) overlay.click();
        }
    """)
    await asyncio.sleep(1)

    return True


async def checkout(page, test_mode=False):
    """
    Single-page checkout flow for kartexpol.pl (Shoper platform):
      1. Navigate to checkout page (via basket → "Dostawa i płatność" or direct URL)
      2. On single checkout page:
         - Select first paczkomat radio button
         - Select BLIK payment radio button
         - Check ALL consent checkboxes
         - Click "Zamawiam i płacę" button
      3. Wait for redirect to payment page (Autopay/Przelewy24/BLIK)
    Returns True if payment page reached.
    """
    # === NAVIGATE TO CHECKOUT ===
    # First try going to basket page and clicking through to checkout
    await page.goto(f"{BASE_URL}/pl/basket", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)
    await dismiss_overlay(page)

    # Check if basket has items — look for checkout-related buttons
    has_items = await page.evaluate("""
        () => {
            const text = document.body.innerText;
            return text.includes('Zamawiam') || text.includes('ZAMAWIAM') ||
                   text.includes('Dostawa i płatność') || text.includes('zamówienie');
        }
    """)
    if not has_items:
        log.error("Basket is empty — no checkout buttons found!")
        return False

    # Click "Dostawa i płatność" or "Zamawiam" button to get to checkout page
    await page.evaluate("""
        () => {
            // Try "Dostawa i płatność" first (popup or basket page button)
            const allBtns = Array.from(document.querySelectorAll('a, button, input[type="submit"]'));
            const dostawaBtn = allBtns.find(el => (el.innerText || el.value || '').includes('Dostawa i płatność'));
            if (dostawaBtn) { dostawaBtn.click(); return; }
            // Fallback: click "ZAMAWIAM" or "Zamawiam" 
            const zamBtn = allBtns.find(el => (el.innerText || el.value || '').toUpperCase().includes('ZAMAWIAM'));
            if (zamBtn) { zamBtn.click(); return; }
            // Last resort: click button.order
            const orderBtn = document.querySelector('button.order');
            if (orderBtn) orderBtn.click();
        }
    """)
    log.info("Clicked checkout button from basket")
    await asyncio.sleep(5)

    # Wait for checkout page to load (may be step2 or a single-page checkout URL)
    deadline = time.time() + 10
    while time.time() < deadline:
        url = page.url
        if "step2" in url or "checkout" in url or "order" in url:
            break
        await asyncio.sleep(1)

    log.info(f"Checkout page URL: {page.url}")
    await dismiss_overlay(page)
    await asyncio.sleep(2)

    # === SINGLE-PAGE CHECKOUT: SELECT PACZKOMAT ===
    # Click the first paczkomat from the list (must click the whole row/label, not just radio)
    try:
        paczkomat_row = page.locator('input[name="nearest_pickup_point"]').first
        await paczkomat_row.click(force=True, timeout=5000)
        log.info("Selected paczkomat (clicked radio via PW)")
    except Exception:
        # Fallback: click the container/label of first paczkomat
        await page.evaluate("""() => {
            const radio = document.querySelector('input[name="nearest_pickup_point"]');
            if (radio) {
                const container = radio.closest('label, li, div.pickup-point, [class*=pickup]') || radio.parentElement;
                if (container) container.click();
                else radio.click();
            }
        }""")
        log.info("Selected paczkomat (JS container click)")
    await asyncio.sleep(3)

    # === SELECT BLIK PAYMENT ===
    try:
        blik_radio = page.locator('input[name="basket_payment"][value="3:509"]')
        await blik_radio.click(force=True, timeout=5000)
        log.info("Selected BLIK payment (PW click)")
    except Exception:
        await page.evaluate("""() => {
            const blik = document.querySelector('input[name="basket_payment"][value="3:509"]');
            if (blik) { blik.closest('label, li, div')?.click() || blik.click(); }
        }""")
        log.info("Selected BLIK payment (JS fallback)")
    await asyncio.sleep(3)

    # === CHECK REQUIRED CONSENT CHECKBOXES ===
    # Check regulamin sklepu (additional_2) + regulamin Paczkomat 24/7 (additional_3 or dynamic)
    # Do NOT check "Chcę otrzymać fakturę" (additional_3 might be invoice)
    checked_count = await page.evaluate("""() => {
        let count = 0;
        const checkboxes = document.querySelectorAll('input[type="checkbox"]');
        for (const cb of checkboxes) {
            // Skip cookie consent checkboxes
            if (cb.name && (cb.name.includes('Consent') || cb.name === 'all')) continue;
            if (cb.id && cb.id.includes('Consent')) continue;
            // Skip invoice checkbox - look for "faktur" in nearby label text
            const label = cb.closest('label') || cb.parentElement;
            const labelText = label ? label.innerText.toLowerCase() : '';
            if (labelText.includes('faktur')) continue;
            // Check required ones (regulamin sklepu + regulamin paczkomat)
            if (!cb.checked) {
                cb.click();
                count++;
            }
        }
        return count;
    }""")
    log.info(f"Checked {checked_count} consent checkboxes (skipped faktura)")
    await asyncio.sleep(2)

    # === CLICK "Zamawiam i płacę" BUTTON ===
    if test_mode:
        # In test mode, verify button exists before clicking
        submit_found = await page.evaluate("""
            () => {
                const allEls = Array.from(document.querySelectorAll('button, input[type="submit"], a'));
                const btn = allEls.find(el => {
                    const text = (el.innerText || el.value || '').toLowerCase();
                    return text.includes('zamawiam i płacę') || text.includes('zamawiam i placę') ||
                           text.includes('zamawiam') || text.includes('złóż zamówienie');
                });
                return !!btn;
            }
        """)
        log.info(f"[TEST MODE] 'Zamawiam i płacę' button found: {submit_found}")
        if not submit_found:
            body = await page.evaluate("() => document.body.innerText.substring(0, 500)")
            log.error(f"[TEST MODE] Submit button not found! Page text: {body[:200]}")
            return False

    # Remove any remaining overlays/modals blocking clicks
    await dismiss_overlay(page)
    await asyncio.sleep(0.5)

    # Click the submit button via PW locator (force=True to bypass any remaining overlays)
    try:
        submit_btn = page.locator('button.btn_primary.btn_full-width').first
        await submit_btn.click(force=True, timeout=10000)
    except Exception:
        # Fallback: JS click
        await page.evaluate("""() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Zamawiam'));
            if (btn) btn.click();
        }""")
    log.info("Clicked 'Zamawiam i płacę'")
    await asyncio.sleep(8)

    # === WAIT FOR PAYMENT PAGE REDIRECT ===
    deadline = time.time() + 20
    while time.time() < deadline:
        url = page.url
        if ("przelewy24" in url or "autopay" in url or "blik" in url or
                "secure.przelewy24" in url or "pay" in url.split("/")[-1:][0] if "/" in url else False):
            prefix = "[TEST MODE] " if test_mode else ""
            log.info(f"{prefix}PAYMENT PAGE REACHED! URL: {url}")
            return True
        await asyncio.sleep(1)

    # Final check
    url = page.url
    if "przelewy24" in url or "autopay" in url or "blik" in url or "secure.przelewy24" in url:
        prefix = "[TEST MODE] " if test_mode else ""
        log.info(f"{prefix}Payment page reached! URL: {url}")
        return True
    else:
        body = await page.evaluate("() => document.body.innerText.substring(0, 300)")
        prefix = "[TEST MODE] " if test_mode else ""
        log.warning(f"{prefix}Payment page not reached. URL: {url}, body: {body[:150]}")
        return False


async def logout(page):
    """
    Logout from kartexpol.pl. Used only for error recovery mid-flow.
    Normal flow just closes the browser context.
    """
    try:
        await page.goto(f"{BASE_URL}/pl/logout", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
    except Exception as e:
        log.warning(f"Logout navigation error: {e}")



# === PRODUCT ID EXTRACTION ===

def extract_product_id(url):
    """
    Extract product ID from URL — last numeric segment of the URL path.
    Examples:
        "https://www.kartexpol.pl/pl/p/Product-Name/12345" → "12345"
        "https://www.kartexpol.pl/pl/p/Some-Product/67890" → "67890"
        "https://example.com/path/no-number" → "no-number" (fallback)
    """
    # Try to find last numeric segment in URL path
    match = re.search(r'/(\d+)(?:[/?#]|$)', url)
    if match:
        return match.group(1)
    # Fallback: use last path segment
    path = url.rstrip('/').split('?')[0].split('#')[0]
    return path.split('/')[-1]


# === ACCOUNT BATCH PROCESSING ===

async def run_for_account_batch(page, account, product_urls, test_mode=False):
    """
    Run full buy flow for one account with MULTIPLE products in one cart.
    
    Returns one of: "success", "skipped", "login_failed", "atc_failed", "checkout_failed"
    """
    email = account["email"]
    name = account["name"]

    # Filter out already completed products
    urls_to_buy = []
    for url in product_urls:
        pid = extract_product_id(url)
        if not is_completed(pid, email):
            urls_to_buy.append(url)

    if not urls_to_buy:
        log.info(f"[{name}] All products already completed, skipping")
        return "skipped"

    log.info(f"[{name}] Starting... ({email}) - {len(urls_to_buy)} products")

    # Login
    ok = await login(page, email, account["password"])
    if not ok:
        log.error(f"[{name}] Login FAILED")
        return "login_failed"
    log.info(f"[{name}] Logged in")

    # Clear cart
    await clear_cart(page)
    log.info(f"[{name}] Cart cleared")

    # Add ALL products to cart
    added = 0
    for url in urls_to_buy:
        ok = await add_to_cart(page, url)
        if ok:
            added += 1
            log.info(f"[{name}] Added: {url.split('/')[-2][:40]}")
        else:
            log.warning(f"[{name}] ATC failed: {url.split('/')[-2][:40]}")

    if added == 0:
        log.error(f"[{name}] No products added to cart!")
        return "atc_failed"

    log.info(f"[{name}] {added}/{len(urls_to_buy)} products in cart")

    # Checkout (all products in one order)
    ok = await checkout(page, test_mode=test_mode)
    if ok:
        log.info(f"[{name}] ORDER PLACED! ({added} products)")
        if not test_mode:
            # Mark all added products as completed
            for url in urls_to_buy:
                pid = extract_product_id(url)
                mark_completed(pid, email)
            await send_discord(f"✅ **{name}** - zamówienie złożone! ({added} produktów)\n💳 Zapłać BLIK na stronie płatności")
        return "success"
    else:
        log.error(f"[{name}] Checkout FAILED")
        return "checkout_failed"


# === MAIN ENTRY POINT ===

async def main():
    parser = argparse.ArgumentParser(description="Kartexpol Auto-Buy Bot")
    parser.add_argument("product_urls", nargs="*", help="Product URL(s) to buy")
    parser.add_argument("--test", action="store_true", help="Use test account (t11008543@gmail.com)")
    parser.add_argument("--accounts", type=int, default=4, help="Number of accounts to process (1-4, default: 4)")
    parser.add_argument("--start", type=int, default=1, help="Start from account number N (1-indexed, 1-4, default: 1)")
    parser.add_argument("--qty", type=int, default=1, help="Quantity per product per account (1-10, default: 1)")
    args = parser.parse_args()

    # Validate: at least one URL required
    if not args.product_urls:
        parser.error("At least one product URL is required")

    # Validate --accounts range (1-4)
    if args.accounts < 1 or args.accounts > 4:
        parser.error(f"--accounts must be between 1 and 4 (got {args.accounts})")

    # Validate --start range (1-4)
    if args.start < 1 or args.start > 4:
        parser.error(f"--start must be between 1 and 4 (got {args.start})")

    # Validate --qty range (1-10)
    if args.qty < 1 or args.qty > 10:
        parser.error(f"--qty must be between 1 and 10 (got {args.qty})")

    # Check DISPLAY environment variable (warn if not :99 but don't block)
    display = os.environ.get("DISPLAY", "")
    if display != ":99":
        log.warning(f"DISPLAY is '{display}' (expected ':99'). Browser may fail without Xvfb.")

    # Build product URL list (repeat URLs based on --qty)
    product_urls = []
    for url in args.product_urls:
        for _ in range(args.qty):
            product_urls.append(url)

    # Select accounts
    if args.test:
        accounts_to_use = [TEST_ACCOUNT]
        log.info("=== TEST MODE (using test account) ===")
    else:
        accounts_to_use = ACCOUNTS[args.start - 1 : args.start - 1 + args.accounts]

    log.info(f"Products ({len(args.product_urls)}):")
    for url in args.product_urls:
        log.info(f"  {url}")
    log.info(f"Accounts: {len(accounts_to_use)}, Qty: {args.qty}, Start: {args.start}")
    log.info(f"Test mode: {args.test}")

    # Notify Discord
    if not args.test:
        prod_list = "\n".join([f"• {url.split('/')[-2][:50]}" for url in args.product_urls])
        await send_discord(f"🚨 **KARTEXPOL AutoBuy** uruchomiony!\n{prod_list}\nKonta: {len(accounts_to_use)}")

    results = []

    for i, account in enumerate(accounts_to_use):
        email = account["email"]
        fp = _engine.get_fingerprint(i)
        proxy = _engine.get_proxy(email)

        log.info(f"[{account['name']}] Browser #{i+1}: proxy={proxy['server'] if proxy else 'DIRECT'}, "
                 f"viewport={fp['viewport']['width']}x{fp['viewport']['height']}")

        async with async_playwright() as p:
            launch_args = {
                "headless": False,
                "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox",
                         "--disable-dev-shm-usage"],
            }
            if proxy:
                launch_args["proxy"] = proxy

            try:
                browser = await p.chromium.launch(**launch_args)
            except Exception as e:
                log.error(f"[{account['name']}] Browser launch failed: {e}")
                if proxy:
                    log.warning(f"[{account['name']}] Retrying without proxy...")
                    launch_args.pop("proxy", None)
                    try:
                        browser = await p.chromium.launch(**launch_args)
                    except Exception as e2:
                        results.append((account["name"], f"error: browser launch failed"))
                        continue
                else:
                    results.append((account["name"], f"error: {e}"))
                    continue

            ctx = await browser.new_context(
                user_agent=fp["user_agent"],
                viewport=fp["viewport"],
                locale=fp["locale"],
                timezone_id=fp["timezone_id"],
            )

            cookies = _engine.load_cookies(email)
            if cookies:
                await ctx.add_cookies(cookies)
                log.info(f"[{account['name']}] Loaded {len(cookies)} pre-warmed cookies")

            page = await ctx.new_page()

            try:
                result = await run_for_account_batch(page, account, product_urls, test_mode=args.test)
                results.append((account["name"], result))
            except Exception as e:
                log.error(f"[{account['name']}] Exception: {e}")
                results.append((account["name"], f"error: {e}"))
            finally:
                await ctx.close()
                await browser.close()

            if i < len(accounts_to_use) - 1:
                delay = random.randint(12, 25)
                log.info(f"Waiting {delay}s before next account (humanizer)...")
                await asyncio.sleep(delay)

    # Summary
    log.info("\n=== SUMMARY ===")
    success_count = 0
    for name, result in results:
        status = "✅" if result == "success" else "❌"
        log.info(f"  {status} {name}: {result}")
        if result == "success":
            success_count += 1

    log.info(f"\nTotal: {success_count}/{len(results)} orders placed")

    # Discord summary
    if not args.test:
        lines = [f"🛒 **Kartexpol AutoBuy** - {success_count}/{len(results)} zamówień!"]
        for name, result in results:
            icon = "✅" if result == "success" else "❌"
            lines.append(f"{icon} {name}: {result}")
        await send_discord("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
