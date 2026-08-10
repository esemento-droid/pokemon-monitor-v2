#!/usr/bin/env python3
"""
Media Expert Auto-Buy Bot
==========================
nodriver + mobile proxy. Sequential accounts twanesek1..N.
Stops when sold out. User pays later via BLIK on each account.

Usage:
    python3 mediaexpert_autobuy.py [--test] [--qty N] [--max N] PRODUCT_URL

Requires: DISPLAY=:99, Xvfb, proxy at 127.0.0.1:8888
"""
import asyncio, sys, os, json, random, re, time, logging, argparse
from datetime import datetime
from pathlib import Path

LOG_FILE = Path(__file__).parent / "mediaexpert_autobuy.log"
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)])
log = logging.getLogger("mediaexpert_bot")

# --- Discord notifications ---
import aiohttp as _aiohttp_dc
WEBHOOK_FILE = Path(__file__).parent / "discord_webhook_mediaexpert.txt"


async def send_discord(msg):
    try:
        if not WEBHOOK_FILE.exists():
            return
        url = WEBHOOK_FILE.read_text().strip()
        if not url:
            return
        async with _aiohttp_dc.ClientSession() as s:
            await s.post(url, json={"content": msg})
    except Exception as e:
        log.warning(f"Discord send failed: {e}")


# === CONFIG ===
PROXY = "http://127.0.0.1:8888"
ACCOUNT_TEMPLATE = {
    "email_prefix": "twanesek", "email_domain": "gmail.com",
    "password": "Senseye.",
    "first_name": "Tomasz", "last_name": "Szczepaniak",
    "street": "Leśna", "building": "46a/2",
    "postal_code": "62-069", "city": "Palędzie", "phone": "607183797",
}
INPOST_POINT = "PAD04M"
QUANTITY = 3
MAX_TOTAL = 50
COMPLETED_FILE = Path(__file__).parent / "mediaexpert_completed.json"
LOCK_FILE = Path(__file__).parent / "mediaexpert_autobuy.lock"



def get_account(n):
    t = ACCOUNT_TEMPLATE
    return {"email": f"{t['email_prefix']}{n}@{t['email_domain']}",
            "password": t["password"], "first_name": t["first_name"],
            "last_name": t["last_name"], "street": t["street"],
            "building": t["building"], "postal_code": t["postal_code"],
            "city": t["city"], "phone": t["phone"]}


def load_completed():
    if COMPLETED_FILE.exists():
        return json.loads(COMPLETED_FILE.read_text())
    return {}


def mark_completed(email, url):
    d = load_completed()
    d.setdefault(email, [])
    if url not in d[email]:
        d[email].append(url)
    COMPLETED_FILE.write_text(json.dumps(d, indent=2))


def is_completed(email, url):
    return url in load_completed().get(email, [])


def get_next_account_number(url):
    d = load_completed()
    for n in range(1, 200):
        e = f"{ACCOUNT_TEMPLATE['email_prefix']}{n}@{ACCOUNT_TEMPLATE['email_domain']}"
        if url not in d.get(e, []):
            return n
    return 1



# === BROWSER HELPERS ===
async def wait_cf(tab, timeout=30):
    """Wait for Cloudflare challenge to resolve."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            title = await tab.evaluate("document.title")
            if "moment" not in title.lower() and "checking" not in title.lower():
                return True
        except Exception:
            pass
        await asyncio.sleep(2)
    log.warning("CF not resolved in %ds", timeout)
    return False


async def dismiss_cookies(tab):
    """Dismiss cookie consent popup."""
    try:
        await tab.evaluate("""
            (() => {
                const bb = document.querySelectorAll('button');
                for (const b of bb) {
                    const t = (b.textContent || '').toLowerCase();
                    if ((t.includes('akceptuj') || t.includes('zgadzam') || t.includes('rozumiem'))
                        && b.offsetParent !== null) {
                        b.click(); return 'clicked';
                    }
                }
                return 'none';
            })()
        """)
        await asyncio.sleep(1)
    except Exception:
        pass



# === REGISTER ===
async def register_account(tab, account):
    """Register a new account on Media Expert."""
    email, password = account["email"], account["password"]
    log.info("[%s] Register -> /rejestracja", email)
    await tab.get("https://www.mediaexpert.pl/rejestracja")
    await asyncio.sleep(5)
    if not await wait_cf(tab, 25):
        log.error("[%s] CF block on register", email)
        return False
    await dismiss_cookies(tab)
    await asyncio.sleep(1)

    # Check if redirected to login (account exists)
    url = await tab.evaluate("window.location.href")
    if "logowanie" in url or "login" in url:
        log.info("[%s] Redirect to login - account exists", email)
        return await login_account(tab, account)

    # Fill registration form
    filled = await tab.evaluate(f"""
        (() => {{
            function setVal(el, val) {{
                if (!el) return false;
                el.focus();
                el.value = '';
                document.execCommand('insertText', false, val);
                el.dispatchEvent(new Event('input', {{bubbles:true}}));
                el.dispatchEvent(new Event('change', {{bubbles:true}}));
                return true;
            }}
            // Email
            const emailEl = document.querySelector('input[type="email"], input[name*="email"], input[name*="login"]');
            setVal(emailEl, '{email}');
            // Password
            const pwEls = document.querySelectorAll('input[type="password"]');
            if (pwEls.length >= 1) setVal(pwEls[0], '{password}');
            if (pwEls.length >= 2) setVal(pwEls[1], '{password}');
            // Checkboxes (terms, marketing)
            document.querySelectorAll('input[type="checkbox"]').forEach(c => {{
                if (!c.checked && c.offsetParent !== null) c.click();
            }});
            return emailEl ? 'ok' : 'no_email_field';
        }})()
    """)
    log.info("[%s] Register fill: %s", email, filled)
    if filled == "no_email_field":
        return False

    await asyncio.sleep(2)

    # Click register button
    await tab.evaluate("""(() => {
        const bb = document.querySelectorAll('button[type="submit"], button');
        for (const b of bb) {
            const t = (b.textContent || '').toLowerCase();
            if ((t.includes('zarejestruj') || t.includes('załóż konto') || t.includes('register'))
                && b.offsetParent !== null && !b.disabled) {
                b.click(); return 'clicked';
            }
        }
        return 'not_found';
    })()""")
    await asyncio.sleep(6)

    new_url = await tab.evaluate("window.location.href")
    if "rejestracja" not in new_url:
        log.info("[%s] Register OK", email)
        return True

    log.warning("[%s] Register may have failed, trying login...", email)
    return await login_account(tab, account)



# === LOGIN ===
async def login_account(tab, account):
    """Login to Media Expert account."""
    email, password = account["email"], account["password"]
    log.info("[%s] Login -> /logowanie", email)
    await tab.get("https://www.mediaexpert.pl/logowanie")
    await asyncio.sleep(5)
    if not await wait_cf(tab, 25):
        log.error("[%s] CF block on login", email)
        return False
    await dismiss_cookies(tab)
    await asyncio.sleep(1)

    # Fill login form using execCommand for framework compatibility
    await tab.evaluate(f"""
        (() => {{
            function setVal(el, val) {{
                if (!el) return false;
                el.focus();
                el.value = '';
                document.execCommand('insertText', false, val);
                el.dispatchEvent(new Event('input', {{bubbles:true}}));
                el.dispatchEvent(new Event('change', {{bubbles:true}}));
                return true;
            }}
            const emailEl = document.querySelector('input[type="email"], input[name*="email"], input[name*="login"], input[id*="email"], input[id*="login"]');
            setVal(emailEl, '{email}');
            const pwEl = document.querySelector('input[type="password"]');
            setVal(pwEl, '{password}');
        }})()
    """)
    await asyncio.sleep(2)

    # Wait for possible captcha/turnstile
    log.info("[%s] Waiting for captcha (5s)...", email)
    await asyncio.sleep(5)

    # Click login button
    await tab.evaluate("""(() => {
        const bb = document.querySelectorAll('button[type="submit"], button');
        for (const b of bb) {
            const t = (b.textContent || '').toLowerCase();
            if ((t.includes('zaloguj') || t.includes('log in') || t.includes('logowanie'))
                && b.offsetParent !== null && !b.disabled) {
                b.click(); return 'clicked';
            }
        }
        return 'not_found';
    })()""")
    await asyncio.sleep(6)

    # Verify login
    new_url = await tab.evaluate("window.location.href")
    if "logowanie" not in new_url and "login" not in new_url:
        log.info("[%s] Login OK", email)
        return True

    # Check cookies
    logged = await tab.evaluate("""
        (() => {
            return document.cookie.includes('session') ||
                   document.cookie.includes('token') ||
                   document.cookie.includes('user');
        })()
    """)
    if logged:
        log.info("[%s] Login OK (cookie)", email)
        return True

    log.error("[%s] Login FAILED url=%s", email, new_url)
    return False



# === CLEAR CART ===
async def clear_cart(tab):
    """Remove all items from cart."""
    log.info("Clearing cart...")
    await tab.get("https://www.mediaexpert.pl/koszyk")
    await asyncio.sleep(4)
    if not await wait_cf(tab, 15):
        return

    # Check if cart is empty
    is_empty = await tab.evaluate("""
        (() => {
            const body = document.body.innerText.toLowerCase();
            return body.includes('koszyk jest pusty') || body.includes('twój koszyk jest pusty')
                || body.includes('brak produktów');
        })()
    """)
    if is_empty:
        log.info("Cart already empty")
        return

    # Remove all items - click delete buttons
    for _ in range(10):
        removed = await tab.evaluate("""
            (() => {
                const btns = document.querySelectorAll('button[class*="delete"], button[class*="remove"], [class*="trash"], [data-testid*="remove"], [aria-label*="usuń"], [aria-label*="Usuń"]');
                if (btns.length > 0) {
                    btns[0].click();
                    return 'clicked';
                }
                // Try links with "usuń"
                const links = document.querySelectorAll('a, button');
                for (const l of links) {
                    const t = (l.textContent || '').toLowerCase().trim();
                    if ((t === 'usuń' || t.includes('usuń produkt')) && l.offsetParent) {
                        l.click();
                        return 'clicked_link';
                    }
                }
                return 'none';
            })()
        """)
        if removed == "none":
            break
        await asyncio.sleep(2)
        # Confirm deletion if dialog appears
        await tab.evaluate("""
            (() => {
                const bb = document.querySelectorAll('button');
                for (const b of bb) {
                    const t = (b.textContent || '').toLowerCase();
                    if ((t.includes('potwierdź') || t.includes('tak') || t === 'usuń')
                        && b.offsetParent !== null) {
                        b.click(); return;
                    }
                }
            })()
        """)
        await asyncio.sleep(2)

    log.info("Cart cleared")



# === ADD TO CART ===
async def add_to_cart(tab, product_url, qty=3):
    """Add product to cart. Returns qty added, -1 if sold out, 0 if failed."""
    log.info("ATC: %s (qty=%d)", product_url, qty)
    await tab.get(product_url)
    await asyncio.sleep(5)
    if not await wait_cf(tab, 20):
        return 0
    await dismiss_cookies(tab)
    await asyncio.sleep(2)

    # Verify on product page
    current_url = await tab.evaluate("window.location.href")
    log.info("ATC page URL: %s", current_url[:120])

    # Check sold out
    avail = await tab.evaluate("""
        (() => {
            const body = document.body.innerText.toLowerCase();
            if (body.includes('produkt niedostępny') || body.includes('wyprzedane')
                || body.includes('brak w magazynie') || body.includes('powiadom o dostępności')
                || body.includes('wycofany z oferty'))
                return 'OUT';
            return 'OK';
        })()
    """)
    if avail == "OUT":
        log.warning("SOLD OUT!")
        return -1

    # Add to cart - click "Do koszyka" / "Dodaj do koszyka" button
    added = 0
    for i in range(qty):
        click_result = await tab.evaluate("""
            (() => {
                // Primary: find ATC button by text
                const bb = document.querySelectorAll('button, a.btn, [role="button"]');
                for (const b of bb) {
                    const t = (b.textContent || '').toLowerCase().trim();
                    if ((t.includes('dodaj do koszyka') || t.includes('do koszyka')
                         || t === 'kup teraz' || t.includes('add to cart'))
                        && b.offsetParent !== null) {
                        if (b.disabled || b.classList.contains('disabled')) return 'disabled';
                        b.click();
                        return 'clicked:' + t.slice(0, 30);
                    }
                }
                // Fallback: data-testid or class-based selectors
                const atc = document.querySelector('[data-testid*="add-to-cart"], [class*="addToCart"], [class*="add-to-cart"], .btn-add-to-cart');
                if (atc && atc.offsetParent !== null) {
                    if (atc.disabled) return 'disabled';
                    atc.click();
                    return 'fallback_clicked';
                }
                return 'none';
            })()
        """)
        log.info("ATC click %d/%d: %s", i + 1, qty, click_result)

        if click_result == "disabled":
            return -1 if added == 0 else added
        if click_result == "none":
            log.warning("ATC button not found!")
            return added if added > 0 else 0

        added += 1
        await asyncio.sleep(3)

        # Close popup/modal if appears (e.g. "Added to cart" confirmation)
        await tab.evaluate("""
            (() => {
                const closers = document.querySelectorAll('[class*="close"], [class*="Close"], [aria-label="Close"], .modal-close, .popup-close');
                for (const c of closers) {
                    if (c.offsetParent !== null) { c.click(); return; }
                }
                // Also try "Kontynuuj zakupy" button
                const bb = document.querySelectorAll('button, a');
                for (const b of bb) {
                    const t = (b.textContent || '').toLowerCase();
                    if (t.includes('kontynuuj zakupy') || t.includes('continue shopping')) {
                        b.click(); return;
                    }
                }
            })()
        """)
        await asyncio.sleep(2)

        # If more than 1 qty, reload product page for next add
        if i < qty - 1:
            await tab.get(product_url)
            await asyncio.sleep(4)
            if not await wait_cf(tab, 15):
                return added

    # Verify cart
    await asyncio.sleep(2)
    await tab.get("https://www.mediaexpert.pl/koszyk")
    await asyncio.sleep(4)
    if not await wait_cf(tab, 15):
        return added

    cart_status = await tab.evaluate("""
        (() => {
            const body = document.body.innerText.toLowerCase();
            if (body.includes('koszyk jest pusty') || body.includes('brak produktów'))
                return 'EMPTY';
            return 'HAS_ITEMS';
        })()
    """)
    if cart_status == "EMPTY":
        log.warning("Cart EMPTY after %d clicks!", added)
        return 0

    log.info("Cart has items, added=%d", added)
    return added



# === CHECKOUT ===
async def checkout(tab, account, test_mode=False):
    """Complete checkout with InPost Paczkomat delivery + BLIK payment."""
    email = account["email"]
    log.info("[%s] Checkout starting...", email)

    # Navigate to cart/checkout
    await tab.get("https://www.mediaexpert.pl/koszyk")
    await asyncio.sleep(4)
    if not await wait_cf(tab, 15):
        return "CF_BLOCK"

    # Check cart not empty
    is_empty = await tab.evaluate("""
        (() => {
            const body = document.body.innerText.toLowerCase();
            return body.includes('koszyk jest pusty') || body.includes('brak produktów');
        })()
    """)
    if is_empty:
        return "CART_EMPTY"

    # Step 1: Click "Przejdź do kasy" / "Zamawiam" / proceed button
    log.info("[%s] Step 1: Proceed to checkout...", email)
    proceed_result = await tab.evaluate("""
        (() => {
            const bb = document.querySelectorAll('button, a.btn, a[class*="btn"]');
            for (const b of bb) {
                const t = (b.textContent || '').toLowerCase().trim();
                if ((t.includes('przejdź do kasy') || t.includes('zamawiam')
                     || t.includes('do kasy') || t.includes('przejdź dalej')
                     || t.includes('złóż zamówienie'))
                    && b.offsetParent !== null && !b.disabled) {
                    b.click();
                    return 'clicked:' + t.slice(0, 30);
                }
            }
            return 'not_found';
        })()
    """)
    log.info("[%s] Proceed: %s", email, proceed_result)

    if "not_found" in proceed_result:
        # Maybe already on checkout page, or need to find link
        await tab.evaluate("""
            (() => {
                const links = document.querySelectorAll('a[href*="zamowienie"], a[href*="checkout"], a[href*="kasa"]');
                if (links.length > 0) links[0].click();
            })()
        """)
        await asyncio.sleep(3)

    await asyncio.sleep(6)

    # Check if login required
    cur_url = await tab.evaluate("window.location.href")
    if "logowanie" in cur_url or "login" in cur_url:
        log.info("[%s] Login required during checkout", email)
        if not await login_account(tab, account):
            return "LOGIN_FAIL"
        await tab.get("https://www.mediaexpert.pl/koszyk")
        await asyncio.sleep(4)
        # Re-click proceed
        await tab.evaluate("""
            (() => {
                const bb = document.querySelectorAll('button, a.btn, a[class*="btn"]');
                for (const b of bb) {
                    const t = (b.textContent || '').toLowerCase().trim();
                    if ((t.includes('przejdź do kasy') || t.includes('zamawiam') || t.includes('do kasy'))
                        && b.offsetParent !== null && !b.disabled) {
                        b.click(); return;
                    }
                }
            })()
        """)
        await asyncio.sleep(6)


    # Step 2: Select delivery method - InPost Paczkomat
    log.info("[%s] Step 2: Select InPost delivery...", email)
    await asyncio.sleep(3)

    # Find and click InPost/Paczkomat option
    inpost_result = await tab.evaluate("""
        (() => {
            const body = document.body.innerText;
            // Find InPost radio/button/label
            const labels = document.querySelectorAll('label, [class*="delivery"], [class*="shipping"], input[type="radio"]');
            for (const el of labels) {
                const t = (el.textContent || '').toLowerCase();
                if (t.includes('inpost') || t.includes('paczkomat')) {
                    el.click();
                    // Also click input inside if label
                    const inp = el.querySelector('input');
                    if (inp) inp.click();
                    return 'clicked_inpost';
                }
            }
            // Try radio buttons with value
            const radios = document.querySelectorAll('input[type="radio"]');
            for (const r of radios) {
                const parent = r.closest('label, div, li');
                if (parent && (parent.textContent || '').toLowerCase().includes('inpost')) {
                    r.click();
                    return 'clicked_radio';
                }
            }
            return 'not_found';
        })()
    """)
    log.info("[%s] InPost select: %s", email, inpost_result)
    await asyncio.sleep(3)

    # Enter Paczkomat point code
    if inpost_result != "not_found":
        await asyncio.sleep(2)
        # Look for paczkomat input field or "Wybierz paczkomat" button
        paczkomat_result = await tab.evaluate(f"""
            (() => {{
                // Try input field for paczkomat code
                const inputs = document.querySelectorAll('input[placeholder*="paczkomat"], input[placeholder*="Paczkomat"], input[name*="point"], input[name*="paczkomat"], input[id*="paczkomat"]');
                for (const inp of inputs) {{
                    if (inp.offsetParent !== null) {{
                        inp.focus();
                        inp.value = '';
                        document.execCommand('insertText', false, '{INPOST_POINT}');
                        inp.dispatchEvent(new Event('input', {{bubbles:true}}));
                        inp.dispatchEvent(new Event('change', {{bubbles:true}}));
                        return 'filled_input';
                    }}
                }}
                // Try "Wybierz paczkomat" button that opens a map/search
                const bb = document.querySelectorAll('button, a');
                for (const b of bb) {{
                    const t = (b.textContent || '').toLowerCase();
                    if ((t.includes('wybierz paczkomat') || t.includes('zmień punkt')
                         || t.includes('wybierz punkt'))
                        && b.offsetParent !== null) {{
                        b.click();
                        return 'opened_picker';
                    }}
                }}
                return 'no_picker';
            }})()
        """)
        log.info("[%s] Paczkomat: %s", email, paczkomat_result)

        if paczkomat_result == "opened_picker":
            await asyncio.sleep(3)
            # Type paczkomat code in search and select
            await tab.evaluate(f"""
                (() => {{
                    const inputs = document.querySelectorAll('input[type="text"], input[type="search"], input[placeholder*="szukaj"], input[placeholder*="wpisz"]');
                    for (const inp of inputs) {{
                        if (inp.offsetParent !== null) {{
                            inp.focus();
                            inp.value = '';
                            document.execCommand('insertText', false, '{INPOST_POINT}');
                            inp.dispatchEvent(new Event('input', {{bubbles:true}}));
                            inp.dispatchEvent(new Event('change', {{bubbles:true}}));
                            return;
                        }}
                    }}
                }})()
            """)
            await asyncio.sleep(3)
            # Click search/confirm
            await tab.evaluate("""
                (() => {
                    const bb = document.querySelectorAll('button, [class*="search"], [class*="confirm"]');
                    for (const b of bb) {
                        const t = (b.textContent || '').toLowerCase();
                        if ((t.includes('szukaj') || t.includes('zatwierdź') || t.includes('wybierz'))
                            && b.offsetParent !== null) {
                            b.click(); return;
                        }
                    }
                })()
            """)
            await asyncio.sleep(3)
            # Select first result
            await tab.evaluate("""
                (() => {
                    const items = document.querySelectorAll('[class*="result"] button, [class*="point"] button, [class*="list-item"] button, li button');
                    if (items.length > 0) { items[0].click(); return; }
                    // Or click the point directly
                    const links = document.querySelectorAll('[class*="result"], [class*="point-name"]');
                    if (links.length > 0) links[0].click();
                })()
            """)
            await asyncio.sleep(2)


    # Step 3: Fill personal data if needed
    log.info("[%s] Step 3: Fill personal data...", email)
    await asyncio.sleep(2)

    await tab.evaluate(f"""
        (() => {{
            function setField(selector, value) {{
                const el = document.querySelector(selector);
                if (el && el.offsetParent !== null && !el.value) {{
                    el.focus();
                    document.execCommand('insertText', false, value);
                    el.dispatchEvent(new Event('input', {{bubbles:true}}));
                    el.dispatchEvent(new Event('change', {{bubbles:true}}));
                }}
            }}
            // Try multiple selector patterns
            const fields = [
                ['input[name*="firstName"], input[name*="first_name"], input[id*="firstName"], input[placeholder*="Imię"]', '{account["first_name"]}'],
                ['input[name*="lastName"], input[name*="last_name"], input[id*="lastName"], input[placeholder*="Nazwisko"]', '{account["last_name"]}'],
                ['input[name*="email"], input[type="email"]', '{email}'],
                ['input[name*="phone"], input[name*="telefon"], input[type="tel"], input[placeholder*="Telefon"]', '{account["phone"]}'],
                ['input[name*="street"], input[name*="ulica"], input[placeholder*="Ulica"]', '{account["street"]}'],
                ['input[name*="building"], input[name*="house"], input[name*="numer"], input[placeholder*="Numer"]', '{account["building"]}'],
                ['input[name*="postal"], input[name*="zip"], input[name*="kod"], input[placeholder*="Kod"]', '{account["postal_code"]}'],
                ['input[name*="city"], input[name*="miasto"], input[placeholder*="Miasto"]', '{account["city"]}'],
            ];
            for (const [sel, val] of fields) {{
                const els = document.querySelectorAll(sel);
                for (const el of els) {{
                    if (el && el.offsetParent !== null && !el.value) {{
                        el.focus();
                        document.execCommand('insertText', false, val);
                        el.dispatchEvent(new Event('input', {{bubbles:true}}));
                        el.dispatchEvent(new Event('change', {{bubbles:true}}));
                        break;
                    }}
                }}
            }}
        }})()
    """)
    await asyncio.sleep(2)

    # Click "Dalej" / "Kontynuuj" / next step
    await tab.evaluate("""
        (() => {
            const bb = document.querySelectorAll('button[type="submit"], button');
            for (const b of bb) {
                const t = (b.textContent || '').toLowerCase().trim();
                if ((t.includes('dalej') || t.includes('kontynuuj') || t.includes('przejdź do płatności')
                     || t.includes('zapisz'))
                    && b.offsetParent !== null && !b.disabled) {
                    b.click(); return 'clicked';
                }
            }
            return 'none';
        })()
    """)
    await asyncio.sleep(5)


    # Step 4: Select payment - BLIK
    log.info("[%s] Step 4: Select BLIK payment...", email)
    await asyncio.sleep(3)

    blik_result = await tab.evaluate("""
        (() => {
            // Find BLIK option
            const labels = document.querySelectorAll('label, [class*="payment"], input[type="radio"], [class*="method"]');
            for (const el of labels) {
                const t = (el.textContent || '').toLowerCase();
                const img = el.querySelector('img');
                const imgAlt = img ? (img.alt || '').toLowerCase() : '';
                if (t.includes('blik') || imgAlt.includes('blik')) {
                    el.click();
                    const inp = el.querySelector('input');
                    if (inp) inp.click();
                    return 'clicked_blik';
                }
            }
            // Try by value
            const radios = document.querySelectorAll('input[type="radio"]');
            for (const r of radios) {
                if ((r.value || '').toLowerCase().includes('blik')) {
                    r.click();
                    return 'clicked_radio_blik';
                }
                const parent = r.closest('label, div, li');
                if (parent && (parent.textContent || '').toLowerCase().includes('blik')) {
                    r.click();
                    return 'clicked_parent_blik';
                }
            }
            return 'not_found';
        })()
    """)
    log.info("[%s] BLIK select: %s", email, blik_result)
    await asyncio.sleep(2)

    # Enter BLIK code (random 6 digits - user will need to confirm on phone)
    blik_code = str(random.randint(100000, 999999))
    blik_input = await tab.evaluate(f"""
        (() => {{
            const inputs = document.querySelectorAll('input[name*="blik"], input[placeholder*="BLIK"], input[placeholder*="kod"], input[maxlength="6"], input[id*="blik"]');
            for (const inp of inputs) {{
                if (inp.offsetParent !== null) {{
                    inp.focus();
                    inp.value = '';
                    document.execCommand('insertText', false, '{blik_code}');
                    inp.dispatchEvent(new Event('input', {{bubbles:true}}));
                    inp.dispatchEvent(new Event('change', {{bubbles:true}}));
                    return 'filled';
                }}
            }}
            return 'no_blik_input';
        }})()
    """)
    log.info("[%s] BLIK code input: %s (code=%s)", email, blik_input, blik_code)
    await asyncio.sleep(2)

    if test_mode:
        log.info("[%s] TEST MODE - skipping final order button", email)
        return "TEST_OK"

    # Step 5: Place order - click final "Zamawiam i płacę" / "Złóż zamówienie"
    log.info("[%s] Step 5: Place order...", email)
    order_result = await tab.evaluate("""
        (() => {
            const bb = document.querySelectorAll('button[type="submit"], button');
            for (const b of bb) {
                const t = (b.textContent || '').toLowerCase().trim();
                if ((t.includes('zamawiam') || t.includes('złóż zamówienie')
                     || t.includes('kupuję i płacę') || t.includes('potwierdź zamówienie'))
                    && b.offsetParent !== null && !b.disabled) {
                    b.click();
                    return 'clicked:' + t.slice(0, 30);
                }
            }
            return 'not_found';
        })()
    """)
    log.info("[%s] Order button: %s", email, order_result)

    if "not_found" in order_result:
        # Debug: show available buttons
        buttons = await tab.evaluate("""
            (() => {
                return Array.from(document.querySelectorAll('button'))
                    .filter(b => b.offsetParent && !b.disabled)
                    .map(b => b.textContent.trim().slice(0, 30))
                    .join(' | ');
            })()
        """)
        log.warning("[%s] Available buttons: %s", email, buttons)
        return "ORDER_BTN_NOT_FOUND"

    await asyncio.sleep(8)

    # Verify order placed
    final_url = await tab.evaluate("window.location.href")
    page_text = await tab.evaluate("document.body.innerText.slice(0, 500)")
    log.info("[%s] Final URL: %s", email, final_url)
    log.info("[%s] Page text: %s", email, str(page_text)[:300])

    if any(word in str(page_text).lower() for word in ["dziękujemy", "zamówienie zostało", "potwierdzenie", "numer zamówienia"]):
        log.info("[%s] ORDER PLACED SUCCESSFULLY!", email)
        return "SUCCESS"

    if "blik" in str(page_text).lower() or "oczekiwanie" in str(page_text).lower():
        log.info("[%s] Waiting for BLIK confirmation", email)
        return "BLIK_PENDING"

    return "UNKNOWN:" + str(final_url)[:100]



# === MAIN BOT LOGIC ===
async def run_bot(product_url, qty=3, max_total=50, test_mode=False):
    """Main bot loop: iterate accounts, add to cart, checkout."""
    import nodriver as uc

    log.info("=" * 60)
    log.info("MEDIA EXPERT BOT START")
    log.info("URL: %s", product_url)
    log.info("QTY per account: %d, MAX total: %d, TEST: %s", qty, max_total, test_mode)
    log.info("=" * 60)

    await send_discord(f"🚀 **ME Bot started**\nURL: {product_url}\nQty: {qty}, Max: {max_total}")

    total_ordered = 0
    sold_out = False
    consecutive_fails = 0

    browser_args = [
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-setuid-sandbox",
        "--window-size=1280,900",
    ]
    if PROXY and PROXY != "none":
        browser_args.append(f"--proxy-server={PROXY}")

    while total_ordered < max_total and not sold_out and consecutive_fails < 5:
        acc_num = get_next_account_number(product_url)
        account = get_account(acc_num)
        email = account["email"]

        if is_completed(email, product_url):
            log.info("[%s] Already completed, skip", email)
            continue

        log.info("=" * 40)
        log.info("[%s] Starting (total so far: %d)", email, total_ordered)

        browser = None
        try:
            browser = await uc.start(headless=False, sandbox=False, browser_args=browser_args)
            tab = await browser.get("about:blank")
            await asyncio.sleep(1)

            # Login or register
            logged_in = await login_account(tab, account)
            if not logged_in:
                log.info("[%s] Login failed, trying register...", email)
                logged_in = await register_account(tab, account)
            if not logged_in:
                log.error("[%s] Cannot login/register, skip", email)
                consecutive_fails += 1
                continue

            # Clear cart
            await clear_cart(tab)

            # Add to cart
            added = await add_to_cart(tab, product_url, qty)
            if added == -1:
                log.warning("SOLD OUT - stopping bot")
                sold_out = True
                await send_discord(f"❌ **ME SOLD OUT!**\n{product_url}")
                break
            if added == 0:
                log.warning("[%s] Failed to add to cart", email)
                consecutive_fails += 1
                continue

            # Checkout
            result = await checkout(tab, account, test_mode)
            log.info("[%s] Checkout result: %s", email, result)

            if result in ("SUCCESS", "BLIK_PENDING", "TEST_OK"):
                mark_completed(email, product_url)
                total_ordered += added
                consecutive_fails = 0
                await send_discord(
                    f"✅ **ME Order** [{email}]\n"
                    f"Qty: {added}, Total: {total_ordered}/{max_total}\n"
                    f"Result: {result}"
                )
            else:
                consecutive_fails += 1
                await send_discord(f"⚠️ **ME Fail** [{email}]: {result}")

        except Exception as e:
            log.error("[%s] Exception: %s", email, e)
            consecutive_fails += 1
        finally:
            if browser:
                try:
                    browser.stop()
                except Exception:
                    pass
            # Small delay between accounts
            await asyncio.sleep(random.uniform(5, 15))

    # Summary
    summary = (
        f"🏁 **ME Bot finished**\n"
        f"Total ordered: {total_ordered}\n"
        f"Sold out: {sold_out}\n"
        f"Fails: {consecutive_fails}"
    )
    log.info(summary.replace("**", "").replace("🏁 ", ""))
    await send_discord(summary)

    return total_ordered



# === CLI ENTRY POINT ===
def main():
    parser = argparse.ArgumentParser(description="Media Expert Auto-Buy Bot")
    parser.add_argument("url", help="Product URL to buy")
    parser.add_argument("--qty", type=int, default=QUANTITY, help="Qty per account")
    parser.add_argument("--max", type=int, default=MAX_TOTAL, help="Max total qty")
    parser.add_argument("--test", action="store_true", help="Test mode (no final order click)")
    args = parser.parse_args()

    # Write lock file
    LOCK_FILE.write_text(str(os.getpid()))

    try:
        result = asyncio.run(run_bot(args.url, args.qty, args.max, args.test))
        log.info("Bot finished. Total ordered: %d", result)
    finally:
        # Remove lock
        try:
            LOCK_FILE.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    main()
