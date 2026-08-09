#!/usr/bin/env python3
"""
TCGumisia Auto-Buy Bot
Platform: Sellingo (tcgumisia.pl)
Method: Patchright headless=False + mobile proxy
Flow: Login (modal) → ATC → Koszyk tab1 (InPost+tpay) → Dane tab2 (regulamin) → Płatność tab3 (Zamawiam)
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

# === CONFIG ===
BASE_URL = "https://tcgumisia.pl"
SHOP_NAME = "tcgumisia"
BOT_DIR = Path(__file__).parent
COMPLETED_FILE = BOT_DIR / "tcgumisia_completed.json"
LOG_FILE = BOT_DIR / "tcgumisia_autobuy.log"
WEBHOOK_FILE = BOT_DIR / "discord_webhook_strefatcg.txt"
PROXY = "http://127.0.0.1:8888"
PACZKOMAT = "PAD04M"

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
log = logging.getLogger("tcgumisia_autobuy")


# === COMPLETED TRACKER ===

def load_completed():
    try:
        if COMPLETED_FILE.exists():
            return json.loads(COMPLETED_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"Failed to load completed file: {e}")
    return {}


def save_completed(data):
    COMPLETED_FILE.write_text(json.dumps(data, indent=2))


def is_completed(product_id, email):
    completed = load_completed()
    return email in completed.get(product_id, [])


def mark_completed(product_id, email):
    completed = load_completed()
    if product_id not in completed:
        completed[product_id] = []
    if email not in completed[product_id]:
        completed[product_id].append(email)
    save_completed(completed)



# === DISCORD NOTIFICATIONS ===

async def send_discord(message):
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

async def login(page, email, password):
    """
    Login via Sellingo modal: click 'Konto' icon → fill E-mail + Hasło → click 'Zaloguj się'
    Selectors from debug: button.js-open-modal[data-aside-target=modal-aside-entry-form],
    form.js-login-form, button.js-submit-login
    """
    for attempt in range(3):
        try:
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)

            # Accept cookies if present
            try:
                cookie_btn = page.locator('.js-accept-cookie-alert-1')
                if await cookie_btn.count() > 0:
                    await cookie_btn.click(timeout=3000)
                    await asyncio.sleep(1)
            except Exception:
                pass

            # Click "Konto" button to open login modal
            try:
                konto_btn = page.locator('button[data-aside-target="modal-aside-entry-form"]')
                await konto_btn.click(timeout=5000)
            except Exception:
                await page.evaluate("""() => {
                    const btn = document.querySelector('button[data-aside-target="modal-aside-entry-form"]');
                    if (btn) btn.click();
                }""")
            await asyncio.sleep(2)

            # Fill email in login form using PW fill() (triggers proper key events)
            email_input = page.locator('.js-login-form input[type="email"], .js-login-form input[placeholder*="E-mail"]').first
            pass_input = page.locator('.js-login-form input[type="password"]').first
            
            await email_input.click(timeout=5000)
            await email_input.fill(email)
            await asyncio.sleep(0.5)
            await pass_input.click(timeout=5000)
            await pass_input.fill(password)
            await asyncio.sleep(0.5)

            # Click "Zaloguj się" button (class: js-submit-login)
            try:
                login_btn = page.locator('.js-submit-login')
                await login_btn.click(timeout=5000)
            except Exception:
                await page.evaluate("""() => {
                    const btn = document.querySelector('.js-submit-login');
                    if (btn) btn.click();
                }""")
            await asyncio.sleep(6)

            # Verify login — check if cart shows a value or account CSS loaded
            # Sellingo doesn't show "wyloguj" on main page, but loads account styles
            page_text = await page.evaluate("() => document.body.innerText")
            
            # Check if cart header shows non-zero value (means session is active with items)
            # OR check if account-aside CSS loaded (sign of successful login)
            logged = await page.evaluate("""() => {
                // Check if account module loaded
                const accountStyle = document.querySelector('link[href*="aside-account"]');
                if (accountStyle) return true;
                // Check response by looking for login error message
                const errorEl = document.querySelector('.js-login-form .error, .js-login-form [class*="error"]');
                if (errorEl && errorEl.innerText.includes('nieprawidłowe')) return false;
                // If modal closed, likely success
                const modal = document.querySelector('.js-login-form');
                if (modal && !modal.closest('.is-active, .is-open, [class*="active"]')) return true;
                return false;
            }""")
            if logged:
                return True

            # Fallback: navigate to /koszyk and see if it shows products or "kup bez rejestracji"
            await page.goto(f"{BASE_URL}/koszyk", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            cart_text = await page.evaluate("() => document.body.innerText.toLowerCase()")
            if "kup bez rejestracji" not in cart_text and "koszyk jest pusty" not in cart_text:
                return True

            log.warning(f"Login attempt {attempt+1} failed for {email}, page_url={page.url}")
        except Exception as e:
            log.warning(f"Login attempt {attempt+1} error for {email}: {e}")

        if attempt < 2:
            await asyncio.sleep(3)

    return False



async def clear_cart(page):
    """Go to /koszyk and click remove buttons for all items."""
    await page.goto(f"{BASE_URL}/koszyk", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(4)

    # Remove items one by one (Sellingo: div.js-cart-product-delete)
    for attempt in range(10):
        # Check if cart is empty
        is_empty = await page.evaluate("""() => {
            const text = document.body.innerText.toLowerCase();
            return text.includes('koszyk jest pusty') || text.includes('brak produktów');
        }""")
        if is_empty:
            log.info("Cart is empty")
            return

        # Click first visible delete button
        clicked = await page.evaluate("""() => {
            const btn = document.querySelector('.js-cart-product-delete');
            if (btn && btn.offsetParent !== null) {
                btn.click();
                return true;
            }
            return false;
        }""")

        if not clicked:
            log.info("No more items to remove")
            return

        log.info(f"Removed item from cart (attempt {attempt+1})")
        await asyncio.sleep(2)

        # Reload to see updated cart
        await page.goto(f"{BASE_URL}/koszyk", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)


async def add_to_cart(page, product_url, qty=1):
    """Navigate to product page and click 'Dodaj do koszyka'. Returns True on success."""
    try:
        await page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        log.warning(f"Failed to load product page {product_url}: {e}")
        return False
    await asyncio.sleep(5)

    # Check for 404
    title = await page.evaluate("() => document.title")
    if "404" in title:
        log.warning(f"Product page 404: {product_url}")
        return False

    # Set quantity if > 1
    if qty > 1:
        try:
            qty_input = page.locator('input[type="number"]').first
            await qty_input.triple_click(timeout=3000)
            await qty_input.fill(str(qty))
            await asyncio.sleep(1)
        except Exception:
            await page.evaluate(f"""() => {{
                const qtyInput = document.querySelector('input[type="number"]');
                if (qtyInput) {{
                    qtyInput.value = '{qty}';
                    qtyInput.dispatchEvent(new Event('input', {{bubbles:true}}));
                    qtyInput.dispatchEvent(new Event('change', {{bubbles:true}}));
                }}
            }}""")
            await asyncio.sleep(1)

    # Click "Dodaj do koszyka" — Sellingo: button#product-card-add-to-card
    clicked = False

    # Method 1: Click by ID (most reliable for Sellingo)
    try:
        atc_btn = page.locator('#product-card-add-to-card')
        if await atc_btn.count() > 0:
            await atc_btn.click(timeout=5000)
            clicked = True
            log.info("ATC clicked via #product-card-add-to-card")
    except Exception as e:
        log.warning(f"ATC by ID failed: {e}")

    # Method 2: Click by JS class
    if not clicked:
        try:
            atc_btn = page.locator('.js-product-card-cart-button')
            if await atc_btn.count() > 0:
                await atc_btn.first.click(timeout=5000)
                clicked = True
                log.info("ATC clicked via .js-product-card-cart-button")
        except Exception as e:
            log.warning(f"ATC by class failed: {e}")

    # Method 3: JS click
    if not clicked:
        clicked = await page.evaluate("""() => {
            const btn = document.getElementById('product-card-add-to-card') ||
                        document.querySelector('.js-product-card-cart-button') ||
                        document.querySelector('.js-add-product-to-card:not(.u-hide)');
            if (btn) { btn.click(); return true; }
            return false;
        }""")
        if clicked:
            log.info("ATC clicked via JS fallback")

    if not clicked:
        log.warning(f"ATC button not found for {product_url}")
        return False

    # Wait for cart popup
    await asyncio.sleep(4)

    # Verify: check cart value changed
    cart_val = await page.evaluate("""() => {
        const el = document.querySelector('.js-cart-value');
        return el ? el.innerText.trim() : '?';
    }""")
    log.info(f"Post-ATC cart value: {cart_val}")

    log.info(f"Added to cart: {product_url.split('/')[-1][:50]}")
    return True



async def checkout(page, account, test_mode=False):
    """
    Sellingo 3-tab checkout:
    Tab 1 (Koszyk): Select InPost Paczkomat + tpay Blik → search PAD04M → Dalej
    Tab 2 (Dane): Data pre-filled, check regulamin → Przejdź dalej
    Tab 3 (Płatność): Confirm → Zamawiam i płacę
    """
    # === Navigate to cart/checkout ===
    await page.goto(f"{BASE_URL}/koszyk", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(4)

    # Check cart has items — look for product names, prices, or quantity inputs
    has_items = await page.evaluate("""() => {
        const text = document.body.innerText;
        // Sellingo cart shows "Metoda dostawy" only when there are items
        // Empty cart says "Twój koszyk jest pusty" or similar
        if (text.includes('koszyk jest pusty') || text.includes('Brak produktów')) return false;
        // Has items if we see delivery method, quantity controls, or product price in cart
        return text.includes('Metoda dostawy') || text.includes('Ilość') || 
               (text.includes('PLN') && text.includes('Dalej'));
    }""")
    if not has_items:
        # Second check - maybe page loaded slowly
        await asyncio.sleep(3)
        has_items = await page.evaluate("""() => {
            const text = document.body.innerText;
            if (text.includes('koszyk jest pusty') || text.includes('Brak produktów')) return false;
            return text.includes('Metoda dostawy') || text.includes('Ilość') || 
                   (text.includes('PLN') && text.includes('Dalej'));
        }""")
    if not has_items:
        body = await page.evaluate("() => document.body.innerText.substring(0, 300)")
        log.error(f"Cart appears empty! Page text: {body[:200]}")
        return False

    # === TAB 1: KOSZYK - Select delivery + payment ===
    log.info("Tab 1: Selecting InPost Paczkomat...")

    # Click InPost Paczkomat radio/option
    await page.evaluate("""() => {
        const labels = Array.from(document.querySelectorAll('label, div, span, li'));
        const inpost = labels.find(el => {
            const text = (el.innerText || '').toLowerCase();
            return text.includes('inpost') || text.includes('paczkomat');
        });
        if (inpost) {
            const radio = inpost.querySelector('input[type="radio"]') || inpost;
            radio.click();
        }
    }""")
    await asyncio.sleep(2)

    # Click "Wyszukaj" button to open paczkomat search
    await page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button, a, span'));
        const searchBtn = btns.find(el => {
            const text = (el.innerText || '').toLowerCase();
            return text.includes('wyszukaj') || text.includes('wybierz punkt');
        });
        if (searchBtn) searchBtn.click();
    }""")
    await asyncio.sleep(2)

    # Type PAD04M in search input
    search_input = page.locator('input[placeholder*="Szukaj"], input[placeholder*="miasto"], input[placeholder*="adres"]').first
    try:
        await search_input.click(timeout=5000)
        await search_input.fill(PACZKOMAT)
        await asyncio.sleep(2)
    except Exception:
        # Fallback: find any visible text input in the paczkomat modal
        await page.evaluate(f"""() => {{
            const inputs = document.querySelectorAll('input[type="text"], input[type="search"]');
            for (const inp of inputs) {{
                if (inp.offsetParent !== null) {{
                    inp.focus();
                    inp.value = '{PACZKOMAT}';
                    inp.dispatchEvent(new Event('input', {{bubbles:true}}));
                    inp.dispatchEvent(new Event('change', {{bubbles:true}}));
                    break;
                }}
            }}
        }}""")
        await asyncio.sleep(2)


    # Select PAD04M from dropdown/results
    await page.evaluate(f"""() => {{
        const items = Array.from(document.querySelectorAll('li, div, span, a, option'));
        const pad = items.find(el => {{
            const text = (el.innerText || el.textContent || '').toUpperCase();
            return text.includes('{PACZKOMAT}') && el.offsetParent !== null;
        }});
        if (pad) pad.click();
    }}""")
    await asyncio.sleep(2)

    # If there's a "Wybierz" button on the point popup, click it
    await page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button, a'));
        const wybierz = btns.find(el => {
            const text = (el.innerText || '').toLowerCase();
            return text.includes('wybierz') && el.offsetParent !== null;
        });
        if (wybierz) wybierz.click();
    }""")
    await asyncio.sleep(2)

    log.info("Tab 1: Selecting tpay Blik payment...")

    # Select tpay / Blik payment method
    await page.evaluate("""() => {
        const labels = Array.from(document.querySelectorAll('label, div, span, li'));
        const tpay = labels.find(el => {
            const text = (el.innerText || '').toLowerCase();
            return text.includes('tpay') || text.includes('blik') || text.includes('karta płatnicza');
        });
        if (tpay) {
            const radio = tpay.querySelector('input[type="radio"]') || tpay;
            radio.click();
        }
    }""")
    await asyncio.sleep(2)

    # Click "Dalej" button (Tab 1 → Tab 2)
    log.info("Tab 1: Clicking Dalej...")
    await page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button, a, input[type="submit"]'));
        const dalej = btns.find(el => {
            const text = (el.innerText || el.value || '').toLowerCase().trim();
            return text === 'dalej' || text.includes('dalej');
        });
        if (dalej) dalej.click();
    }""")
    await asyncio.sleep(4)


    # === TAB 2: DANE - Fill data if needed, check regulamin, click Przejdź dalej ===
    log.info("Tab 2: Checking/filling data...")

    # Wait for Tab 2 to load
    await asyncio.sleep(2)

    # Fill address data if fields are empty (Sellingo may not pre-fill even for logged users)
    # Account data mapping
    ACCOUNT_DATA = {
        "esemento@gmail.com": {"first": "Tomasz", "last": "Szczepaniak", "street": "Leśna", "number": "46a/2", "zip": "62-069", "city": "Palędzie", "phone": "607183797"},
        "blackmat36@gmail.com": {"first": "Natalia", "last": "Szczepaniak", "street": "Leśna", "number": "46a/2", "zip": "62-069", "city": "Palędzie", "phone": "607183797"},
        "tjbtaniojuzbylo@gmail.com": {"first": "Jagoda", "last": "Kaczmarek", "street": "Leśna", "number": "46a/2", "zip": "62-069", "city": "Palędzie", "phone": "607183797"},
        "y24015411@gmail.com": {"first": "Miroslawa", "last": "Szczepaniak", "street": "Leśna", "number": "46a/2", "zip": "62-069", "city": "Palędzie", "phone": "607183797"},
        "t11008543@gmail.com": {"first": "Marian", "last": "Wasilewski", "street": "Konduktorska", "number": "14", "zip": "00-775", "city": "Warszawa", "phone": "672245321"},
    }
    email = account["email"]
    data = ACCOUNT_DATA.get(email, ACCOUNT_DATA["t11008543@gmail.com"])
    
    await page.evaluate(f"""() => {{
        function fillIfEmpty(selector, value) {{
            const els = document.querySelectorAll(selector);
            for (const el of els) {{
                if (el.offsetParent !== null && !el.value.trim()) {{
                    el.focus();
                    el.value = value;
                    el.dispatchEvent(new Event('input', {{bubbles:true}}));
                    el.dispatchEvent(new Event('change', {{bubbles:true}}));
                    el.dispatchEvent(new Event('blur', {{bubbles:true}}));
                }}
            }}
        }}
        fillIfEmpty('input[name="name"], input[name="first_name"], input[placeholder*="Imię"]', '{data["first"]}');
        fillIfEmpty('input[name="surname"], input[name="last_name"], input[placeholder*="Nazwisko"]', '{data["last"]}');
        fillIfEmpty('input[name="street"], input[placeholder*="Ulica"]', '{data["street"]}');
        fillIfEmpty('input[name="building_number"], input[name="street_number"], input[placeholder*="Numer domu"]', '{data["number"]}');
        fillIfEmpty('input[name="zip_code"], input[name="postcode"], input[placeholder*="Kod"]', '{data["zip"]}');
        fillIfEmpty('input[name="city"], input[placeholder*="Miasto"]', '{data["city"]}');
        fillIfEmpty('input[name="phone"], input[placeholder*="Telefon"]', '{data["phone"]}');
        fillIfEmpty('input[name="email"], input[placeholder*="E-mail"], input[type="email"]', '{email}');
    }}""")
    await asyncio.sleep(1)

    # Check regulamin checkbox (required) - skip faktura and newsletter
    await page.evaluate("""() => {
        const checkboxes = document.querySelectorAll('input[type="checkbox"]');
        for (const cb of checkboxes) {
            const label = cb.closest('label') || cb.parentElement;
            const labelText = label ? label.innerText.toLowerCase() : '';
            // Check regulamin (required)
            if (labelText.includes('regulamin') || labelText.includes('oświadczam') || labelText.includes('akceptuj')) {
                if (!cb.checked) cb.click();
            }
        }
    }""")
    await asyncio.sleep(1)

    # Click "Przejdź dalej" button (Tab 2 → Tab 3)
    log.info("Tab 2: Clicking Przejdź dalej...")
    await page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button, a, input[type="submit"]'));
        const dalej = btns.find(el => {
            const text = (el.innerText || el.value || '').toLowerCase();
            return text.includes('przejdź dalej') || text.includes('przejdz dalej');
        });
        if (dalej) dalej.click();
    }""")
    await asyncio.sleep(4)

    # === TAB 3: PŁATNOŚĆ - Confirm and submit ===
    log.info("Tab 3: Płatność - confirming order...")
    await asyncio.sleep(2)

    # Verify we're on payment tab
    on_payment = await page.evaluate("""() => {
        const text = document.body.innerText.toLowerCase();
        return text.includes('zamawiam i płacę') || text.includes('zamawiam') || text.includes('podsumowanie');
    }""")
    if not on_payment:
        log.warning("May not be on payment tab, attempting anyway...")

    if test_mode:
        submit_found = await page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button, a, input[type="submit"]'));
            return btns.some(el => {
                const text = (el.innerText || el.value || '').toLowerCase();
                return text.includes('zamawiam');
            });
        }""")
        log.info(f"[TEST MODE] 'Zamawiam i płacę' button found: {submit_found}")
        if not submit_found:
            body = await page.evaluate("() => document.body.innerText.substring(0, 500)")
            log.error(f"[TEST MODE] Submit button not found! Page text: {body[:200]}")
            return False
        # TEST MODE: click submit to verify full flow (real order on test account!)
        log.info("[TEST MODE] Clicking 'Zamawiam i płacę' (real order on test account)")


    # Click "Zamawiam i płacę" button
    await page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button, a, input[type="submit"]'));
        const submit = btns.find(el => {
            const text = (el.innerText || el.value || '').toLowerCase();
            return text.includes('zamawiam i płacę') || text.includes('zamawiam i placę') || text.includes('zamawiam');
        });
        if (submit) submit.click();
    }""")
    log.info("Clicked 'Zamawiam i płacę'")
    await asyncio.sleep(8)

    # Wait for redirect to payment gateway (tpay)
    deadline = time.time() + 20
    while time.time() < deadline:
        url = page.url
        if ("tpay" in url or "przelewy24" in url or "autopay" in url or
                "blik" in url or "pay" in url or "platnosc" in url):
            log.info(f"PAYMENT PAGE REACHED! URL: {url}")
            return True
        await asyncio.sleep(1)

    # Final check
    url = page.url
    if any(kw in url for kw in ["tpay", "przelewy24", "autopay", "blik", "pay", "platnosc"]):
        log.info(f"Payment page reached! URL: {url}")
        return True

    # Check if order was placed (sometimes no redirect, just confirmation page)
    body = await page.evaluate("() => document.body.innerText.substring(0, 500)")
    if "dziękujemy" in body.lower() or "zamówienie" in body.lower() or "potwierdzenie" in body.lower():
        log.info(f"Order confirmed (no redirect)! Page: {body[:100]}")
        return True

    log.warning(f"Payment page not reached. URL: {url}, body: {body[:150]}")
    return False



# === PRODUCT ID EXTRACTION ===

def extract_product_id(url):
    """Extract product slug from tcgumisia URL."""
    # URL format: https://tcgumisia.pl/pokemon-tcg-something-something/75
    path = url.rstrip('/').split('?')[0].split('#')[0]
    path = re.sub(r'/\d+$', '', path)  # Remove trailing /75 etc
    slug = path.split('/')[-1]
    return slug


# === ACCOUNT PROCESSING ===

async def run_for_account(page, account, product_urls, qty, test_mode=False):
    """
    Run full buy flow for one account.
    Returns: "success", "skipped", "login_failed", "atc_failed", "checkout_failed"
    """
    email = account["email"]
    name = account["name"]

    # Filter already completed
    urls_to_buy = []
    for url in product_urls:
        pid = extract_product_id(url)
        if not is_completed(pid, email):
            urls_to_buy.append(url)

    if not urls_to_buy:
        log.info(f"[{name}] All products already completed, skipping")
        return "skipped"

    log.info(f"[{name}] Starting... ({email}) - {len(urls_to_buy)} products, qty={qty}")

    # Login
    ok = await login(page, email, account["password"])
    if not ok:
        log.error(f"[{name}] Login FAILED")
        return "login_failed"
    log.info(f"[{name}] Logged in")

    # Clear cart
    await clear_cart(page)
    log.info(f"[{name}] Cart cleared")

    # Add products to cart
    added = 0
    for url in urls_to_buy:
        ok = await add_to_cart(page, url, qty=qty)
        if ok:
            added += 1
        else:
            log.warning(f"[{name}] ATC failed: {url.split('/')[-1][:40]}")

    if added == 0:
        log.error(f"[{name}] No products added to cart!")
        return "atc_failed"

    log.info(f"[{name}] {added}/{len(urls_to_buy)} products in cart")

    # Checkout
    ok = await checkout(page, account, test_mode=test_mode)
    if ok:
        log.info(f"[{name}] ORDER PLACED! ({added} products)")
        if not test_mode:
            for url in urls_to_buy:
                pid = extract_product_id(url)
                mark_completed(pid, email)
            await send_discord(f"✅ **{name}** - tcgumisia zamówienie złożone! ({added} produktów)\n💳 Zapłać na stronie płatności (tpay/BLIK)")
        return "success"
    else:
        log.error(f"[{name}] Checkout FAILED")
        return "checkout_failed"



# === MAIN ENTRY POINT ===

async def main():
    parser = argparse.ArgumentParser(description="TCGumisia Auto-Buy Bot")
    parser.add_argument("product_urls", nargs="*", help="Product URL(s) to buy")
    parser.add_argument("--test", action="store_true", help="Use test account, don't submit order")
    parser.add_argument("--accounts", type=int, default=4, help="Number of accounts (1-4, default: 4)")
    parser.add_argument("--start", type=int, default=1, help="Start from account N (1-4, default: 1)")
    parser.add_argument("--qty", type=int, default=1, help="Quantity per product (1-10, default: 1)")
    args = parser.parse_args()

    if not args.product_urls:
        parser.error("At least one product URL is required")
    if args.accounts < 1 or args.accounts > 4:
        parser.error(f"--accounts must be 1-4 (got {args.accounts})")
    if args.start < 1 or args.start > 4:
        parser.error(f"--start must be 1-4 (got {args.start})")
    if args.qty < 1 or args.qty > 10:
        parser.error(f"--qty must be 1-10 (got {args.qty})")

    display = os.environ.get("DISPLAY", "")
    if display != ":99":
        log.warning(f"DISPLAY is '{display}' (expected ':99')")

    # Select accounts
    if args.test:
        accounts_to_use = [TEST_ACCOUNT]
        log.info("=== TEST MODE (using test account, will NOT submit) ===")
    else:
        accounts_to_use = ACCOUNTS[args.start - 1 : args.start - 1 + args.accounts]

    log.info(f"Products ({len(args.product_urls)}):")
    for url in args.product_urls:
        log.info(f"  {url}")
    log.info(f"Accounts: {len(accounts_to_use)}, Qty: {args.qty}")

    # Discord notify
    if not args.test:
        prod_list = "\n".join([f"• {url.split('/')[-1][:50]}" for url in args.product_urls])
        await send_discord(f"🚨 **TCGUMISIA AutoBuy** uruchomiony!\n{prod_list}\nKonta: {len(accounts_to_use)}, qty: {args.qty}")

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', f'--proxy-server={PROXY}']
        )

        for i, account in enumerate(accounts_to_use):
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            )
            page = await ctx.new_page()

            try:
                result = await run_for_account(page, account, args.product_urls, args.qty, test_mode=args.test)
                results.append((account["name"], result))
            except Exception as e:
                log.error(f"[{account['name']}] Exception: {e}")
                results.append((account["name"], f"error: {e}"))
            finally:
                await ctx.close()

            if i < len(accounts_to_use) - 1:
                await asyncio.sleep(2)

        await browser.close()

    # Summary
    log.info("\n=== SUMMARY ===")
    success_count = 0
    for name, result in results:
        status = "✅" if result == "success" else "❌"
        log.info(f"  {status} {name}: {result}")
        if result == "success":
            success_count += 1

    log.info(f"\nTotal: {success_count}/{len(results)} orders placed")

    if not args.test:
        lines = [f"🛒 **TCGumisia AutoBuy** - {success_count}/{len(results)} zamówień!"]
        for name, result in results:
            icon = "✅" if result == "success" else "❌"
            lines.append(f"{icon} {name}: {result}")
        await send_discord("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
