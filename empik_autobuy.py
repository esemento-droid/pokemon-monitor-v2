#!/usr/bin/env python3
"""
Empik Auto-Buy Bot
==================
nodriver + mobile proxy. Sequential accounts twanesek1..N.
Stops when sold out. User pays later via BLIK on each account.

Usage:
    python3 empik_autobuy.py [--test] [--qty N] [--max N] PRODUCT_URL

Requires: DISPLAY=:99, Xvfb, proxy at 127.0.0.1:8888
"""
import asyncio, sys, os, json, random, re, time, logging, argparse
from datetime import datetime
from pathlib import Path

LOG_FILE = Path(__file__).parent / "empik_autobuy.log"
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)])
log = logging.getLogger("empik")
# --- Discord notifications ---
import aiohttp as _aiohttp_dc
WEBHOOK_FILE_EMPIK = Path(__file__).parent / "discord_webhook_empik.txt"

async def send_discord_empik(msg):
    try:
        if not WEBHOOK_FILE_EMPIK.exists():
            return
        url = WEBHOOK_FILE_EMPIK.read_text().strip()
        if not url:
            return
        async with _aiohttp_dc.ClientSession() as s:
            await s.post(url, json={"content": msg})
    except Exception as e:
        log.warning(f"Discord send failed: {e}")
# --- end Discord ---


# === CONFIG ===
from bot_engine import BotEngine
_engine = BotEngine(shop="empik")

def _get_proxy_for_account(email=""):
    """Get proxy URL for nodriver --proxy-server arg."""
    url = _engine.get_proxy_url(email)
    return url or "http://127.0.0.1:8888"

PROXY = _get_proxy_for_account()  # Default, overridden per-account in run_one()
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
DISCORD_WEBHOOK = None
COMPLETED_FILE = Path(__file__).parent / "empik_completed.json"


# React-compatible value setter (React ignores direct .value = x)
REACT_SET = """
function reactSet(el, val) {
    var ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    ns.call(el, val);
    el.dispatchEvent(new Event('input', {bubbles:true}));
    el.dispatchEvent(new Event('change', {bubbles:true}));
}
"""

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
    if url not in d[email]: d[email].append(url)
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
    try:
        await tab.evaluate("""
            (() => {
                const bb = document.querySelectorAll('button');
                for (const b of bb) {
                    const t = b.textContent.toLowerCase();
                    if ((t.includes('akceptuj') || t.includes('zgadzam')) && b.offsetParent !== null)
                        { b.click(); return; }
                }
            })()
        """)
        await asyncio.sleep(1)
    except Exception:
        pass


# === REGISTER ===
async def register_account(tab, account):
    email, password = account["email"], account["password"]
    log.info("[%s] Register -> /konto/rejestracja", email)
    await tab.get("https://www.empik.com/konto/rejestracja")
    await asyncio.sleep(4)
    if not await wait_cf(tab, 25):
        log.error("[%s] CF block", email)
        return False
    await dismiss_cookies(tab)
    await asyncio.sleep(1)

    url = await tab.evaluate("window.location.href")
    if "logowanie" in url:
        log.info("[%s] Redirect to login - account exists", email)
        return await login_account(tab, account)

    # Fill email + password using React setter
    fill = await tab.evaluate(f"""
        (() => {{
            {REACT_SET}
            let r = [];
            // email
            const em = document.querySelectorAll('input[type="email"], input[name="email"], input[autocomplete="email"]');
            for (const i of em) {{ if (i.offsetParent !== null) {{ reactSet(i, '{email}'); r.push('e'); break; }} }}
            // password
            const pw = document.querySelectorAll('input[type="password"]');
            for (const i of pw) {{ if (i.offsetParent !== null) {{ reactSet(i, '{password}'); r.push('p'); }} }}
            // checkboxes
            document.querySelectorAll('input[type="checkbox"]').forEach(c => {{
                if (!c.checked && c.offsetParent !== null) c.click();
            }});
            r.push('cb');
            return r.join(',');
        }})()
    """)
    log.info("[%s] Fill: %s", email, fill)
    await asyncio.sleep(1)

    # Turnstile
    log.info("[%s] Turnstile wait 7s...", email)
    await asyncio.sleep(7)

    # Submit
    sub = await tab.evaluate("""
        (() => {
            const bb = document.querySelectorAll('button[type="submit"], button');
            for (const b of bb) {
                const t = (b.textContent||'').toLowerCase();
                if ((t.includes('załóż konto') || t.includes('zarejest') || t.includes('utwórz'))
                    && b.offsetParent !== null && !b.disabled)
                    { b.click(); return 'ok:' + b.textContent.trim().slice(0,20); }
            }
            return 'no_btn';
        })()
    """)
    log.info("[%s] Submit: %s", email, sub)
    await asyncio.sleep(6)

    # Check
    new_url = await tab.evaluate("window.location.href")
    body = await tab.evaluate("(document.body||{}).innerText?.slice(0,500)||''")

    if "hasło jest wymagane" in body.lower() or "wprowadź adres" in body.lower():
        log.warning("[%s] Validation error - trying keyboard input...", email)
        ok = await _type_fields(tab, email, password)
        if ok:
            await asyncio.sleep(7)
            await tab.evaluate("""(() => {
                const bb = document.querySelectorAll('button');
                for (const b of bb) { if (b.textContent.toLowerCase().includes('załóż') && b.offsetParent) { b.click(); return; } }
            })()""")
            await asyncio.sleep(6)
            new_url = await tab.evaluate("window.location.href")
            body = await tab.evaluate("(document.body||{}).innerText?.slice(0,500)||''")

    if "już istnieje" in body.lower() or "posiadasz już konto" in body.lower():
        log.info("[%s] Account exists -> login", email)
        return await login_account(tab, account)

    if "rejestracja" not in new_url:
        log.info("[%s] Register OK! URL: %s", email, new_url)
        return True

    # Check cookie
    logged = await tab.evaluate("document.cookie.includes('access_token')")
    if logged:
        log.info("[%s] Logged in (cookie)", email)
        return True

    log.warning("[%s] Register FAILED. URL=%s body=%s", email, new_url, body[:150])
    return False


async def _type_fields(tab, email, password):
    """Type into fields using CDP Input.dispatchKeyEvent as fallback."""
    try:
        # Focus email field
        await tab.evaluate("""(() => {
            const em = document.querySelectorAll('input[type="email"], input[name="email"]');
            for (const i of em) { if (i.offsetParent !== null) { i.focus(); i.value=''; return 'ok'; } }
            return 'no';
        })()""")
        await asyncio.sleep(0.3)
        # Type email
        for ch in email:
            await tab.send("Input.dispatchKeyEvent", type="keyDown", text=ch)
            await tab.send("Input.dispatchKeyEvent", type="keyUp", text=ch)
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.3)
        # Focus password
        await tab.evaluate("""(() => {
            const pw = document.querySelectorAll('input[type="password"]');
            for (const i of pw) { if (i.offsetParent !== null) { i.focus(); i.value=''; return; } }
        })()""")
        await asyncio.sleep(0.3)
        for ch in password:
            await tab.send("Input.dispatchKeyEvent", type="keyDown", text=ch)
            await tab.send("Input.dispatchKeyEvent", type="keyUp", text=ch)
            await asyncio.sleep(0.02)
        # Checkboxes
        await tab.evaluate("""(() => {
            document.querySelectorAll('input[type="checkbox"]').forEach(c => {
                if (!c.checked && c.offsetParent !== null) c.click();
            });
        })()""")
        return True
    except Exception as e:
        log.warning("_type_fields error: %s", e)
        return False


# === LOGIN ===
async def login_account(tab, account):
    email, password = account["email"], account["password"]
    log.info("[%s] Login...", email)
    await tab.get("https://www.empik.com/logowanie")
    await asyncio.sleep(4)
    if not await wait_cf(tab, 25):
        return False
    await dismiss_cookies(tab)
    await asyncio.sleep(1)

    await tab.evaluate(f"""
        (() => {{
            {REACT_SET}
            const em = document.querySelectorAll('input[type="email"], input[name="login"], input[name="email"]');
            for (const i of em) {{ if (i.offsetParent !== null) {{ reactSet(i, '{email}'); break; }} }}
            const pw = document.querySelectorAll('input[type="password"]');
            for (const i of pw) {{ if (i.offsetParent !== null) {{ reactSet(i, '{password}'); break; }} }}
        }})()
    """)
    await asyncio.sleep(1)
    log.info("[%s] Turnstile 7s...", email)
    await asyncio.sleep(7)

    await tab.evaluate("""(() => {
        const bb = document.querySelectorAll('button[type="submit"], button');
        for (const b of bb) {
            const t = b.textContent.toLowerCase();
            if ((t.includes('zaloguj') || t.includes('log in')) && b.offsetParent !== null && !b.disabled)
                { b.click(); return; }
        }
    })()""")
    await asyncio.sleep(6)

    new_url = await tab.evaluate("window.location.href")
    if "logowanie" not in new_url:
        log.info("[%s] Login OK", email)
        return True
    logged = await tab.evaluate("document.cookie.includes('access_token')")
    if logged:
        log.info("[%s] Login OK (cookie)", email)
        return True
    log.error("[%s] Login FAILED url=%s", email, new_url)
    return False


# === ADD TO CART ===
async def add_to_cart(tab, product_url, qty=3):
    """Returns qty added, -1 if sold out, 0 if failed."""
    log.info("ATC: %s (qty=%d)", product_url, qty)
    await tab.get(product_url)
    await asyncio.sleep(4)
    if not await wait_cf(tab, 20):
        return 0
    await dismiss_cookies(tab)
    await asyncio.sleep(1)

    # Verify we're actually on the product page
    current_url = await tab.evaluate("window.location.href")
    log.info("ATC page URL: %s", current_url[:100])
    if "p1" not in current_url and ",p" not in current_url:
        # CF redirected us - try again
        log.warning("Not on product page, retrying navigation...")
        await tab.get(product_url)
        await asyncio.sleep(5)
        if not await wait_cf(tab, 20):
            return 0
        current_url = await tab.evaluate("window.location.href")
        log.info("ATC page URL (retry): %s", current_url[:100])
        if ",p" not in current_url:
            log.error("Cannot reach product page! URL: %s", current_url)
            return 0
    await asyncio.sleep(2)

    # Check sold out
    avail = await tab.evaluate("""(() => {
        const b = document.body.innerText.toLowerCase();
        if (b.includes('produkt niedostępny') || b.includes('wyprzedane') ||
            b.includes('brak w magazynie') || b.includes('powiadom o dostępności'))
            return 'OUT';
        return 'OK';
    })()""")
    if avail == "OUT":
        log.warning("SOLD OUT!")
        return -1

    # GraphQL add (all qty at once)
    pid = re.search(r',p(\d+),', product_url)
    pid = pid.group(1) if pid else None
    # Check for offerId and shopId in URL (marketplace products)
    oid_match = re.search(r'offerId=(\d+)', product_url)
    offer_id = oid_match.group(1) if oid_match else None
    shop_match = re.search(r'mpShopId=(\d+)', product_url)
    shop_id = shop_match.group(1) if shop_match else "0"
    # If no offerId in URL, try to extract from page
    if not offer_id:
        offer_id = await tab.evaluate("""
            (() => {
                // Check meta tags, data attributes, or page scripts
                const meta = document.querySelector('meta[name="empik:offerId"], [data-offer-id]');
                if (meta) return meta.content || meta.getAttribute('data-offer-id');
                // Check URL params on ATC button
                const atc = document.querySelector('[data-offerid], [data-offer-id]');
                if (atc) return atc.getAttribute('data-offerid') || atc.getAttribute('data-offer-id');
                // Check page source for offerId
                const scripts = document.querySelectorAll('script');
                for (const s of scripts) {
                    const m = (s.textContent || '').match(/"offerId"\s*:\s*"?(\d+)"?/);
                    if (m) return m[1];
                }
                // Check URL in canonical/og
                const canon = document.querySelector('link[rel="canonical"]');
                if (canon) {
                    const cm = canon.href.match(/offerId=(\d+)/);
                    if (cm) return cm[1];
                }
                return null;
            })()
        """)
        if offer_id:
            log.info("Extracted offerId from page: %s", offer_id)
    log.info("Product ID: %s, Offer ID: %s, Shop ID: %s", pid, offer_id, shop_id)

    if offer_id or pid:
        # Use AddProductsToCart with offerId for marketplace, AddProductItemsToCart for empik direct
        if offer_id:
            gql_mutation = f"""
                window._gql = 'pending';
                fetch('/gateway/api/graphql/cart', {{
                    method:'POST', headers:{{'Content-Type':'application/json'}},
                    body:JSON.stringify({{
                        operationName:'AddProductsToCart',
                        variables:{{input:{{items:[{{offerId:"{offer_id}",quantity:{qty}}}],premiumInCart:false}}}},
                        query:'mutation AddProductsToCart($input:AddItemsToCartInput!){{addItemsToCart(addItemsToCartInput:$input){{miniCart{{productCount}}}}}}'
                    }})
                }}).then(r=>r.json()).then(d=>{{
                    if(d.errors) window._gql='err:'+JSON.stringify(d.errors).slice(0,100);
                    else window._gql='ok:'+(d?.data?.addItemsToCart?.miniCart?.productCount||0);
                }}).catch(e=>{{window._gql='exc:'+e.message;}});
            """
        else:
            gql_mutation = f"""
                window._gql = 'pending';
                fetch('/gateway/api/graphql/cart', {{
                    method:'POST', headers:{{'Content-Type':'application/json'}},
                    body:JSON.stringify({{
                        operationName:'AddProductItemsToCart',
                        variables:{{input:{{items:[{{productId:"{pid}",quantity:{qty}}}],premiumInCart:false}}}},
                        query:'mutation AddProductItemsToCart($input:AddProductItemsToCartInput!){{addProductItemsToCart(addProductItemsToCartInput:$input){{miniCart{{productCount}}}}}}'
                    }})
                }}).then(r=>r.json()).then(d=>{{
                    if(d.errors) window._gql='err:'+JSON.stringify(d.errors).slice(0,100);
                    else window._gql='ok:'+(d?.data?.addProductItemsToCart?.miniCart?.productCount||0);
                }}).catch(e=>{{window._gql='exc:'+e.message;}});
            """
        await tab.evaluate(gql_mutation)
        # Wait for result
        for _ in range(15):
            await asyncio.sleep(1)
            r = await tab.evaluate("window._gql")
            if r and r != "pending":
                break
        log.info("GraphQL: %s", str(r)[:150])
        if str(r).startswith("ok:"):
            return qty
        if "sold" in str(r).lower() or "unavailable" in str(r).lower():
            return -1
        # GraphQL error - fall through to click method
        log.info("GraphQL failed, trying /ajax/mp/dodaj-do-koszyka...")

    # Try legacy ATC endpoint
    if pid:
        await tab.evaluate(f"""
            window._atc2 = 'pending';
            fetch('/ajax/mp/dodaj-do-koszyka', {{
                method:'POST', headers:{{'Content-Type':'application/json'}},
                credentials:'same-origin',
                body:JSON.stringify({{productId:"{pid}", quantity:{qty}, shopId:"{shop_id if 'shop_id' in dir() else '0'}"}})
            }}).then(r=>r.json()).then(d=>{{window._atc2='ok:'+JSON.stringify(d).slice(0,100);}}).catch(e=>{{window._atc2='exc:'+e.message;}});
            }}).then(r=>r.json()).then(d=>{{window._atc2='ok:'+JSON.stringify(d).slice(0,100);}}).catch(e=>{{window._atc2='exc:'+e.message;}});
        """)
        for _ in range(8):
            await asyncio.sleep(1)
            r2 = await tab.evaluate("window._atc2")
            if r2 and r2 != "pending":
                break
        log.info("Legacy ATC: %s", str(r2)[:150])
        if str(r2).startswith("ok:") and "error" not in str(r2).lower() and "forbidden" not in str(r2).lower():
            return qty
        log.info("Legacy ATC failed too, trying button clicks...")

    # Fallback: click button
    added = 0
    # Wait for page to fully load (CF might still be resolving)
    await asyncio.sleep(3)
    # Debug: what's on the product page - show ALL buttons with class and disabled state
    page_debug = await tab.evaluate("""(() => {
        const btns = document.querySelectorAll('button, a.btn, [role="button"]');
        const info = [];
        for (const b of btns) {
            if (b.offsetParent !== null) {
                const t = (b.textContent||'').trim().replace(/\\s+/g,' ').slice(0,40);
                if (t.length > 0) info.push((b.disabled?'[DIS]':'[EN]') + t);
            }
        }
        const cartBadge = document.querySelector('.mini-cart-count, [data-ta="ta-goto-cart-btn"]');
        const cartN = cartBadge ? cartBadge.textContent.trim() : '?';
        return 'url:'+window.location.href.slice(0,60)+' cart:'+cartN+' btns:'+info.slice(0,25).join(' | ');
    })()""")
    log.info("PRODUCT PAGE: %s", str(page_debug)[:500])

    for i in range(qty):
        cr = await tab.evaluate("""(() => {
            const bb = document.querySelectorAll('button, a.btn, [role="button"]');
            for (const b of bb) {
                const t = (b.textContent || '').toLowerCase().trim();
                if ((t.includes('dodaj do koszyka') || t.includes('do koszyka') || t === 'kup teraz')
                    && b.offsetParent !== null) {
                    if (b.disabled || b.classList.contains('disabled')) return 'disabled';
                    b.click(); return 'clicked:' + t.slice(0,25);
                }
            }
            // Try data-ta selectors
            const atc = document.querySelector('[data-ta="ta-tab-addtocart"], .addToCart, [class*="addToCart"]');
            if (atc && atc.offsetParent !== null) {
                if (atc.disabled) return 'disabled';
                atc.click(); return 'ta_clicked';
            }
            return 'none';
        })()""")
        if cr == "disabled": return -1 if added == 0 else added
        if cr == "none":
            log.warning("ATC button not found on page!")
            return added
        added += 1
        log.info("ATC click %d/%d", i+1, qty)
        await asyncio.sleep(2)
        await tab.evaluate("(() => { const c = document.querySelector('.modal-close,.popup-close'); if(c) c.click(); })()")
        await asyncio.sleep(1)

    # Verify cart has items after clicks
    await asyncio.sleep(2)
    cart_check = await tab.evaluate("""(() => {
        // Check mini-cart count in header
        const els = document.querySelectorAll('[class*="cart"] span, [class*="Cart"] span, [data-ta*="cart"]');
        for (const e of els) {
            const n = parseInt(e.textContent.trim());
            if (!isNaN(n) && n > 0) return 'items:' + n;
        }
        // Check via fetch
        return 'checking';
    })()""")
    log.info("Cart badge: %s", cart_check)

    # If cart seems empty, navigate to /koszyk to verify
    if "items:" not in str(cart_check):
        await tab.get("https://www.empik.com/koszyk")
        await asyncio.sleep(4)
        if not await wait_cf(tab, 15):
            await asyncio.sleep(3)
        cart_page = await tab.evaluate("""(() => {
            const body = document.body.innerText.slice(0, 500);
            if (body.includes('Twój koszyk jest pusty') || body.includes('koszyk jest pusty'))
                return 'EMPTY';
            if (body.includes('Przejdź do kasy') || body.includes('Zamów'))
                return 'HAS_ITEMS';
            return 'body:' + body.slice(0,200);
        })()""")
        log.info("Cart page: %s", str(cart_page)[:200])
        if cart_page == "EMPTY":
            log.warning("Cart is EMPTY after %d clicks!", added)
            return 0

    return added



# === CHECKOUT (React SPA at /cart/) ===

# === CHECKOUT ===
async def checkout(tab, account, test_mode=False):
    email = account["email"]
    log.info("[%s] Checkout -> /cart/", email)
    await tab.get("https://www.empik.com/cart/")
    await asyncio.sleep(5)
    if not await wait_cf(tab, 15):
        await asyncio.sleep(5)

    cur_url = await tab.evaluate("window.location.href")
    if "logowanie" in cur_url:
        if not await login_account(tab, account):
            return "LOGIN_FAIL"
        await tab.get("https://www.empik.com/cart/")
        await asyncio.sleep(5)

    # Step 1: Find and click proceed to delivery button
    log.info("[%s] Step 1: proceed to delivery...", email)
    await asyncio.sleep(3)

    # DUMP the bottom part of page (CTA button is usually at bottom)
    page_bottom = await tab.evaluate("document.body.innerHTML.slice(-3000)")
    log.info("[%s] CART HTML (last 3000): %s", email, str(page_bottom)[:3000])

    # Click proceed button: [data-ta="proceed-button"] = "Wybierz sposob dostawy"
    proceed = await tab.evaluate("""(() => {
        const btn = document.querySelector('[data-ta="proceed-button"]');
        if (!btn) return 'not_found';
        const text = btn.textContent.trim().slice(0, 40);
        btn.click();
        return 'clicked:' + text;
    })()""")
    log.info("[%s] Proceed btn: %s", email, str(proceed)[:200])

    if "not_found" in str(proceed):
        # Debug: show all data-ta elements
        all_ta = await tab.evaluate("(() => { return Array.from(document.querySelectorAll('[data-ta]')).map(e=>e.getAttribute('data-ta')+':'+e.textContent.trim().slice(0,20)).join(' | '); })()")
        log.info("[%s] All data-ta: %s", email, str(all_ta)[:500])
        return "PROCEED_NOT_FOUND"

    await asyncio.sleep(6)

    # Check page state - marketplace may show purchase-button directly or delivery form
    log.info("[%s] Checking delivery page...", email)
    await asyncio.sleep(3)

    page_info = await tab.evaluate("""(() => {
        const txt = document.body.innerText.substring(0, 1500);
        const pb = document.querySelector('[data-ta="purchase-button"]');
        const dataTas = Array.from(document.querySelectorAll('[data-ta]')).map(e => e.getAttribute('data-ta')+':'+e.textContent.trim().slice(0,15)).join(', ');
        const btns = Array.from(document.querySelectorAll('button')).filter(b=>b.offsetParent&&!b.disabled).map(b=>b.textContent.trim().slice(0,25)).join(' | ');
        const hasDelivery = txt.includes('InPost') || txt.includes('Paczkomat') || txt.includes('Kurier');
        const hasPurchase = pb && pb.offsetParent && !pb.disabled;
        return JSON.stringify({hasDelivery, hasPurchase, btns, dataTas, txt: txt.slice(0, 800)});
    })()""")
    log.info("[%s] Page: %s", email, str(page_info)[:1000])

    import json as _json
    try:
        info = _json.loads(page_info)
    except:
        info = {}

    if info.get("hasPurchase"):
        log.info("[%s] Purchase button ready! Marketplace direct order.", email)
        # Click Zatwierdź to confirm address data first
        zatw_r = await tab.evaluate("""(() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                if (b.offsetParent && !b.disabled && b.textContent.trim() === 'Zatwierdź') {
                    b.click(); return 'clicked';
                }
            }
            return 'not_found';
        })()""")
        log.info("[%s] Zatwierdź: %s", email, zatw_r)
        await asyncio.sleep(5)

        # After Zatwierdź: form fields are now visible. Fill them with React-compatible events.
        t = ACCOUNT_TEMPLATE
        phone = t["phone"]
        fill_r = await tab.evaluate("""(() => {
            const ns = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            function f(name, value) {
                const inp = document.querySelector('input[name="' + name + '"]');
                if (!inp || !inp.offsetParent) return 'miss';
                if (inp.value && inp.value.length > 2 && inp.value !== '+48') return 'has:'+inp.value.slice(0,8);
                // Focus the input first
                inp.focus();
                // Set value using native setter
                ns.call(inp, value);
                // Dispatch React-compatible events
                inp.dispatchEvent(new Event('focus', {bubbles: true}));
                inp.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: value}));
                inp.dispatchEvent(new Event('change', {bubbles: true}));
                inp.dispatchEvent(new Event('blur', {bubbles: true}));
                return 'ok';
            }
            return [
                'fn:'+f('firstName','""" + t["first_name"] + """'),
                'ln:'+f('lastName','""" + t["last_name"] + """'),
                'ph:'+f('phoneNumber','""" + phone + """'),
                'st:'+f('street','""" + t["street"] + """'),
                'hn:'+f('houseNo','""" + t["building"] + """'),
                'pc:'+f('postalCode','""" + t["postal_code"] + """'),
                'ci:'+f('city','""" + t["city"] + """')
            ].join(', ');
        })()""")
        log.info("[%s] Fill: %s", email, fill_r)
        await asyncio.sleep(1)

        # Type city value using keyboard (React needs real key events for some fields)
        city_val = t["city"]
        type_r = await tab.evaluate("""(() => {
            // Focus city input and clear it
            const inp = document.querySelector('input[name="city"]');
            if (!inp || !inp.offsetParent) return 'city_miss';
            inp.focus();
            inp.select();
            // Delete current content
            document.execCommand('selectAll', false, null);
            document.execCommand('delete', false, null);
            // Insert text using execCommand (triggers React state update)
            document.execCommand('insertText', false, '""" + city_val + """');
            return 'typed:' + inp.value;
        })()""")
        log.info("[%s] City type: %s", email, type_r)
        await asyncio.sleep(1)

        # Also do the same for ALL fields that might have same issue
        # Use execCommand insertText for every field (safest React method)
        retype_r = await tab.evaluate("""(() => {
            function typeInto(name, value) {
                const inp = document.querySelector('input[name="' + name + '"]');
                if (!inp || !inp.offsetParent) return 'miss';
                if (inp.value === value) return 'same';
                inp.focus();
                document.execCommand('selectAll', false, null);
                document.execCommand('delete', false, null);
                document.execCommand('insertText', false, value);
                inp.dispatchEvent(new Event('blur', {bubbles: true}));
                return 'retyped:' + inp.value.slice(0,10);
            }
            return [
                'fn:'+typeInto('firstName','""" + t["first_name"] + """'),
                'ln:'+typeInto('lastName','""" + t["last_name"] + """'),
                'st:'+typeInto('street','""" + t["street"] + """'),
                'hn:'+typeInto('houseNo','""" + t["building"] + """'),
                'pc:'+typeInto('postalCode','""" + t["postal_code"] + """'),
                'ci:'+typeInto('city','""" + city_val + """'),
                'ph:'+(function(){const inp=document.querySelector('input[name="phoneNumber"]');if(!inp||!inp.offsetParent)return 'miss';const ns=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;const formatted='+48 607 183 797';ns.call(inp,formatted);inp.dispatchEvent(new Event('input',{bubbles:true}));inp.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:formatted}));inp.dispatchEvent(new Event('change',{bubbles:true}));inp.dispatchEvent(new Event('blur',{bubbles:true}));return 'set:'+inp.value.slice(0,15);})()
            ].join(', ');
        })()""")
        log.info("[%s] Retype all: %s", email, retype_r)
        await asyncio.sleep(2)

        # Click Zatwierdź again to submit filled form
        zatw2 = await tab.evaluate("""(() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                if (b.offsetParent && !b.disabled && b.textContent.trim() === 'Zatwierdź') {
                    b.click(); return 'clicked2';
                }
            }
            return 'not_found2';
        })()""")
        log.info("[%s] Zatwierdź #2: %s", email, zatw2)
        await asyncio.sleep(5)

        # Check state after second Zatwierdź
        state2 = await tab.evaluate("""(() => {
            const txt = document.body.innerText.substring(0, 600);
            const btns = Array.from(document.querySelectorAll('button')).filter(b=>b.offsetParent&&!b.disabled).map(b=>b.textContent.trim().slice(0,25)).join(' | ');
            const hasDel = txt.includes('InPost') || txt.includes('Paczkomat') || txt.includes('Kurier');
            const hasErr = txt.includes('Wprowadź') || txt.includes('Pole wymagane') || txt.includes('nieprawidłow');
            return JSON.stringify({hasDel, hasErr, btns, txt: txt.slice(0,400)});
        })()""")
        log.info("[%s] After fill+Zatwierdź: %s", email, str(state2)[:600])

        # Scroll down to reveal delivery section (below address)
        await tab.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(3)

        # Click delivery option by data-ta attribute (PACKSTATION = InPost Paczkomat)
        delivery_r = await tab.evaluate("""(() => {
            // First try empik-delivery PACKSTATION
            const packs = document.querySelectorAll('[data-ta="PACKSTATION"]');
            for (const p of packs) {
                if (p.offsetParent) { p.click(); return 'clicked:PACKSTATION:' + p.textContent.trim().slice(0, 30); }
            }
            // Fallback: any delivery method
            const methods = document.querySelectorAll('[data-ta="STORE"], [data-ta="POST"], [data-ta="COURIER"]');
            for (const m of methods) {
                if (m.offsetParent) { m.click(); return 'clicked_fallback:' + m.getAttribute('data-ta') + ':' + m.textContent.trim().slice(0, 30); }
            }
            // Debug: list all data-ta with delivery
            const all = document.querySelectorAll('[data-ta]');
            const del_tas = [];
            for (const el of all) {
                const ta = el.getAttribute('data-ta');
                if (ta && (ta.includes('delivery') || ta.includes('PACK') || ta.includes('STORE') || ta.includes('POST') || ta.includes('COURIER'))) {
                    del_tas.push(ta + ':' + (el.offsetParent ? 'vis' : 'hid'));
                }
            }
            return 'not_found:' + del_tas.join(', ');
        })()""")
        log.info("[%s] Delivery select: %s", email, str(delivery_r)[:300])
        await asyncio.sleep(3)

        # If PACKSTATION clicked, modal appears - select InPost filter + search + pick point
        if "PACKSTATION" in str(delivery_r):
            # InPost filter chip (A tag)
            await asyncio.sleep(2)
            filter_r = await tab.evaluate("""(() => {
                const chips = document.querySelectorAll('a, button, [role=tab], [role=button]');
                for (const c of chips) {
                    const t = (c.textContent || '').trim();
                    if (t.includes('InPost') && t.includes('Paczkomat') && c.offsetParent) {
                        c.click();
                        return 'clicked:' + c.tagName + ':' + t;
                    }
                }
                return 'no_inpost_chip';
            })()""")
            log.info("[%s] InPost filter: %s", email, filter_r)
            await asyncio.sleep(2)

            # Type PAD04M in search
            search_r = await tab.evaluate("""(() => {
                const inputs = document.querySelectorAll('input');
                for (const inp of inputs) {
                    if (!inp.offsetParent) continue;
                    const ph = (inp.placeholder || '').toLowerCase();
                    if (ph.includes('miejscowo') || ph.includes('kod pocztowy') || ph.includes('wyszukaj')) {
                        inp.focus();
                        document.execCommand('selectAll', false, null);
                        document.execCommand('delete', false, null);
                        document.execCommand('insertText', false, 'PAD04M');
                        return 'typed:' + inp.value;
                    }
                }
                return 'no_search_input';
            })()""")
            log.info("[%s] Search: %s", email, search_r)
            await asyncio.sleep(4)

            # Click PAD04M point row (custom CSS radio, NOT input[type=radio])
            # Row contains "PAD04M" + "Pal" but NOT "salon" or "Wszystkie"
            point_r = await tab.evaluate("""(() => {
                const candidates = [];
                const all = document.querySelectorAll('*');
                for (let i = 0; i < all.length; i++) {
                    const el = all[i];
                    if (!el.offsetParent) continue;
                    const t = el.textContent || '';
                    if (t.includes('PAD04M') && !t.includes('salon') && !t.includes('Wszystkie') && !t.includes('InPost Paczkomat 24/7')) {
                        candidates.push({el, len: t.length, tag: el.tagName, cls: el.className});
                    }
                }
                if (candidates.length === 0) return 'no_pad04m_on_page';
                candidates.sort((a,b) => a.len - b.len);
                // Pick element between 5-120 chars (the point row itself)
                for (const c of candidates) {
                    if (c.len >= 5 && c.len <= 120) {
                        c.el.click();
                        return 'clicked:' + c.tag + ':' + c.len + ':' + (c.cls||'').slice(0,30) + ':' + c.el.textContent.trim().slice(0,60);
                    }
                }
                candidates[0].el.click();
                return 'fallback:' + candidates[0].tag + ':' + candidates[0].len;
            })()""")
            log.info("[%s] Paczkomat select: %s", email, point_r)
            await asyncio.sleep(3)

            # Confirm selection if button exists
            confirm_r = await tab.evaluate("""(() => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    const t = (b.textContent || '').trim().toLowerCase();
                    if (b.offsetParent && (t === 'wybierz' || t === 'zatwierdź' || t === 'potwierdź' || t.includes('wybierz punkt') || t.includes('zapisz'))) {
                        b.click();
                        return 'confirmed:' + t;
                    }
                }
                return 'no_confirm_btn';
            })()""")
            log.info("[%s] Confirm: %s", email, confirm_r)
            await asyncio.sleep(3)


        # Take screenshot after scroll + delivery selection
        try:
            import base64 as b64mod
            import nodriver.cdp.page as cdp_page
            ss_data = await tab.send(cdp_page.capture_screenshot(format_="png"))
            with open("/tmp/empik_debug.png", "wb") as f:
                f.write(b64mod.b64decode(ss_data))
            log.info("[%s] Screenshot saved after delivery", email)
        except Exception as e:
            log.info("[%s] SS error: %s", email, e)

        # Deep debug: check what blocks the order
        debug = await tab.evaluate("""(() => {
            const r = {};
            // 1. All checkboxes (might need terms acceptance)
            const cbs = document.querySelectorAll('input[type=checkbox]');
            r.checkboxes = Array.from(cbs).map(c => ({
                name: c.name, id: c.id, checked: c.checked, 
                vis: !!c.offsetParent, required: c.required,
                label: c.closest('label')?.textContent?.trim().slice(0,40) || c.nextElementSibling?.textContent?.trim().slice(0,40) || ''
            }));
            // 2. Any error/validation messages visible
            const errs = document.querySelectorAll('[class*=error], [class*=Error], [role=alert], [class*=invalid], [class*=warning]');
            r.errors = Array.from(errs).filter(e => e.offsetParent && e.textContent.trim().length > 0).map(e => e.textContent.trim().slice(0, 60));
            // 3. Purchase button state
            const pb = document.querySelector('[data-ta="purchase-button"]');
            if (pb) {
                r.purchaseBtn = {
                    disabled: pb.disabled,
                    ariaDisabled: pb.getAttribute('aria-disabled'),
                    className: pb.className?.slice(0, 60),
                    parentClass: pb.parentElement?.className?.slice(0, 40)
                };
            }
            // 4. Form inputs that are empty but required
            const inputs = document.querySelectorAll('input:not([type=hidden]):not([type=checkbox])');
            r.emptyInputs = Array.from(inputs).filter(i => i.offsetParent && !i.value && i.required).map(i => i.name || i.placeholder);
            // 5. Any delivery-related elements (radio, select)
            const radios = document.querySelectorAll('input[type=radio]');
            r.radios = Array.from(radios).map(rd => ({name: rd.name, val: rd.value?.slice(0,15), checked: rd.checked, vis: !!rd.offsetParent}));
            // 6. Scroll position + page height
            r.scroll = {top: window.scrollY, pageH: document.body.scrollHeight, winH: window.innerHeight};
            return JSON.stringify(r);
        })()""")
        log.info("[%s] DEEP DEBUG: %s", email, str(debug)[:1500])

        if test_mode:
            # Take screenshot for debugging
            try:
                import base64 as b64mod
                import nodriver.cdp.page as cdp_page
                ss_data = await tab.send(cdp_page.capture_screenshot(format_="png"))
                with open("/tmp/empik_debug.png", "wb") as f:
                    f.write(b64mod.b64decode(ss_data))
                log.info("[%s] Screenshot: /tmp/empik_debug.png", email)
            except Exception as e:
                log.info("[%s] Screenshot failed: %s", email, e)
            log.info("[%s] TEST MODE - deep debug done", email)
            return "TEST_OK"
        # Select BLIK payment + enter random code
        await asyncio.sleep(2)
        blik_r = await tab.evaluate("""(() => {
            const all = document.querySelectorAll('button,label,div,li,span,[role=radio]');
            for (const el of all) {
                const t = (el.textContent || '').trim();
                if (t === 'BLIK' && el.offsetParent) {
                    el.click();
                    const r = el.querySelector('input[type=radio]');
                    if (r) r.click();
                    return 'clicked';
                }
            }
            return 'none';
        })()""")
        log.info("[%s] BLIK: %s", email, blik_r)
        await asyncio.sleep(2)
        blik_code = f"{random.randint(100000, 999999)}"
        log.info("[%s] BLIK code: %s", email, blik_code)
        await tab.evaluate(f"""(() => {{
            const ns = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
            const inputs = document.querySelectorAll('input[inputmode=numeric],input[type=tel],input[maxlength="6"]');
            for (const inp of inputs) {{
                if (inp.offsetParent) {{
                    ns.call(inp, '{blik_code}');
                    inp.dispatchEvent(new Event('input', {{bubbles:true}}));
                    inp.dispatchEvent(new Event('change', {{bubbles:true}}));
                    return 'ok';
                }}
            }}
            return 'no_input';
        }})()""")
        await asyncio.sleep(1)

        # Enter BLIK code and click "Płacę Blikiem"
        import random as _rnd
        blik_code = str(_rnd.randint(100000, 999999))
        log.info("[%s] BLIK code: %s", email, blik_code)
        blik_input = await tab.evaluate(f"""(() => {{
            // Find BLIK input by data-ta attribute
            const inp = document.querySelector('[data-ta="blik-input"] input') || document.querySelector('[data-ta="blik-input"]') || document.querySelector('input[name*="blik"],input[placeholder*="BLIK"],input[placeholder*="kod"]');
            if (inp && inp.offsetParent) {{
                inp.focus();
                document.execCommand('selectAll', false, null);
                document.execCommand('insertText', false, '{blik_code}');
                return 'typed:' + inp.value;
            }}
            // Fallback: any visible input near Płacę Blikiem
            const all = document.querySelectorAll('input');
            for (const i of all) {{
                if (!i.offsetParent || i.type==='hidden' || i.type==='checkbox') continue;
                if (!i.value && i.closest('[class*=blik],[class*=Blik],[class*=payment]')) {{
                    i.focus();
                    document.execCommand('selectAll', false, null);
                    document.execCommand('insertText', false, '{blik_code}');
                    return 'fallback:' + i.value;
                }}
            }}
            return 'no_blik_input';
        }})()""")
        log.info("[%s] BLIK input: %s", email, blik_input)
        await asyncio.sleep(2)

        # Click "Płacę Blikiem" button
        order_r = await tab.evaluate("""(() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                const t = (b.textContent || '').trim();
                if (b.offsetParent && (t.includes('Płacę Blik') || t.includes('lacę Blik'))) {
                    b.click();
                    return 'clicked:' + t;
                }
            }
            // Fallback: purchase-button
            const pb = document.querySelector('[data-ta="purchase-button"]');
            if (pb && pb.offsetParent && !pb.disabled) {
                pb.click();
                return 'fallback_purchase:' + pb.textContent.trim().slice(0,30);
            }
            return 'no_btn';
        })()""")
        log.info("[%s] ORDER CLICK: %s", email, order_r)
        await asyncio.sleep(8)
        # Check result
        url = await tab.evaluate("window.location.href")
        body = await tab.evaluate("document.body.innerText.substring(0, 400)")
        log.info("[%s] After order URL: %s", email, url)
        log.info("[%s] After order body: %s", email, body[:200])
        if "dziekujemy" in body.lower() or "potwierdzenie" in url or "confirmation" in url:
            return "ORDER_PLACED"
        if "blik" in body.lower() or "platnosc" in body.lower() or "payment" in url.lower():
            return "PAYMENT_PENDING"
        return "ORDER_SUBMITTED"
    elif info.get("hasDelivery"):
        log.info("[%s] Delivery visible", email)
    else:
        # Wait for page to load
        for i in range(15):
            await asyncio.sleep(3)
            chk = await tab.evaluate("""(() => {
                const pb = document.querySelector('[data-ta="purchase-button"]');
                if (pb && pb.offsetParent && !pb.disabled) return 'purchase_ready';
                const txt = document.body.innerText;
                if (txt.includes('InPost') || txt.includes('Paczkomat') || txt.includes('Kurier')) return 'delivery_visible';
                if (txt.includes('Dane odbiorcy')) return 'address_form:' + txt.substring(0, 150);
                return 'wait:' + txt.substring(0, 150);
            })()""")
            log.info("[%s] Wait #%d: %s", email, i+1, str(chk)[:150])
            if "purchase_ready" in str(chk) or "delivery_visible" in str(chk):
                break
        else:
            log.error("[%s] Checkout stuck", email)
            return "CHECKOUT_FAIL"

    # Step 2: Select InPost Paczkomat
    log.info("[%s] Step 2: InPost...", email)
    inpost = await tab.evaluate("(() => { const all=document.querySelectorAll('button,label,div,li,span,[role=radio]'); for(const el of all){const t=(el.textContent||'').trim(); if(t.includes('InPost')&&t.includes('Paczkomat')&&el.offsetParent&&t.length<80){el.click(); const r=el.querySelector('input[type=radio]'); if(r)r.click(); return 'clicked:'+t.slice(0,40);}} return 'not_found'; })()")
    log.info("[%s] InPost: %s", email, inpost)
    await asyncio.sleep(3)

    # Search paczkomat by point ID
    log.info("[%s] Paczkomat search: %s...", email, INPOST_POINT)
    point = INPOST_POINT
    # Clear and type point ID
    search_res = await tab.evaluate("(() => { const inputs=document.querySelectorAll('input[type=text],input[type=search],input[placeholder]'); for(const inp of inputs){ const ph=(inp.placeholder||'').toLowerCase(); if(inp.offsetParent&&(ph.includes('kod')||ph.includes('adres')||ph.includes('wyszukaj')||ph.includes('miasto')||ph.includes('pocztowy')||ph.includes('miejscowo'))){inp.focus();inp.value='';inp.dispatchEvent(new Event('input',{bubbles:true}));document.execCommand('insertText',false,'" + point + "');inp.dispatchEvent(new Event('change',{bubbles:true}));return 'typed:'+inp.value;}} return 'no_input'; })()")
    log.info("[%s] Search: %s", email, search_res)
    await asyncio.sleep(4)

    # Select point from results - click radio/row containing PAD04M
    select_res = await tab.evaluate("(() => { const all=document.querySelectorAll('div,li,label,span,article'); for(const el of all){ const t=el.textContent||''; if(t.includes('" + point + "')&&el.offsetParent&&t.length<200){ const radio=el.querySelector('input[type=radio],input[type=checkbox]'); if(radio){radio.click();return 'radio:'+t.trim().slice(0,60);} el.click(); return 'el:'+el.tagName+':'+t.trim().slice(0,60);}} const radios=document.querySelectorAll('input[type=radio]'); for(const r of radios){ const p=r.closest('div,li,label'); if(p&&p.textContent.includes('" + point + "')){r.click();return 'radio_p:'+p.textContent.trim().slice(0,60);}} const items=[]; radios.forEach((r,i)=>{const p=r.closest('div,li');if(p&&p.offsetParent)items.push(i+':'+p.textContent.trim().slice(0,25));}); return 'not_found|radios:'+items.join(';'); })()")
    log.info("[%s] Point select: %s", email, select_res)
    await asyncio.sleep(2)

    # Confirm point selection
    confirm_res = await tab.evaluate("(() => { const btns=document.querySelectorAll('button,a[role=button]'); for(const b of btns){ const t=(b.textContent||'').trim().toLowerCase(); if(b.offsetParent&&(t==='wybierz'||t==='zatwierdź'||t==='potwierdź'||t.includes('wybierz punkt')||t.includes('zapisz'))){b.click();return 'confirmed:'+t;}} return 'no_confirm_btn'; })()")
    log.info("[%s] Confirm: %s", email, confirm_res)
    await asyncio.sleep(3)

    # Step 3: BLIK
    log.info("[%s] Step 3: BLIK...", email)
    await tab.evaluate("(() => { const all=document.querySelectorAll('button,label,div,li,span,[role=radio]'); for(const el of all){const t=(el.textContent||'').trim(); if(t==='BLIK'&&el.offsetParent){el.click(); const r=el.querySelector('input[type=radio]'); if(r)r.click(); return 'ok';}} return 'none'; })()")
    await asyncio.sleep(2)

    blik_code = f"{random.randint(100000, 999999)}"
    log.info("[%s] BLIK code: %s", email, blik_code)
    await tab.evaluate(f"(() => {{ const ns=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set; const inputs=document.querySelectorAll('input[inputmode=numeric],input[type=tel],input[maxlength=\'6\']'); for(const inp of inputs){{ if(inp.offsetParent){{ ns.call(inp,'{blik_code}'); inp.dispatchEvent(new Event('input',{{bubbles:true}})); inp.dispatchEvent(new Event('change',{{bubbles:true}})); return 'ok'; }} }} return 'none'; }})()")
    await asyncio.sleep(1)

    # Terms
    await tab.evaluate("(() => { document.querySelectorAll('input[type=checkbox]').forEach(c => { if(!c.checked&&c.offsetParent) c.click(); }); })()")
    await asyncio.sleep(1)

    if test_mode:
        log.info("[%s] TEST - not ordering", email)
        txt = await tab.evaluate("document.body.innerText.slice(0,300)")
        log.info("[%s] Page: %s", email, str(txt)[:200])
        return "TEST_OK"

    # Step 4: Order
    log.info("[%s] ORDERING!", email)
    await tab.evaluate("(() => { const all=document.querySelectorAll('button,[role=button]'); for(const el of all){const t=(el.textContent||'').trim().toLowerCase(); if((t.includes('zamawiam')||t.includes('kupuj')||t.includes('zap'))&&el.offsetParent&&!el.disabled&&t.length<40){el.click();return 'ok';}} return 'none'; })()")
    await asyncio.sleep(8)

    body = await tab.evaluate("document.body ? document.body.innerText.slice(0,400) : ''")
    url = await tab.evaluate("window.location.href")
    if "dziekujemy" in body.lower() or "zamowienie" in body.lower():
        log.info("[%s] ORDER PLACED! %s", email, url)
        return "ORDER_PLACED"
    if "blik" in body.lower() or "zaplac" in body.lower():
        log.info("[%s] Awaiting payment", email)
        return "PAYMENT_PENDING"
    log.warning("[%s] Unclear: %s", email, body[:150])
    return "UNCLEAR"


async def run_one(account, product_url, qty, test_mode):
    import nodriver as uc
    email = account["email"]
    log.info("=" * 50)
    log.info("[%s] START", email)

    browser = await uc.start(headless=False, browser_args=[
        f"--proxy-server={_get_proxy_for_account(email)}", "--no-first-run", "--no-default-browser-check",
        "--disable-popup-blocking", "--disable-extensions", "--window-size=1280,900"])
    try:
        tab = browser.main_tab

        # Auth (direct login - accounts pre-registered)
        auth = await login_account(tab, account)
        if not auth:
            return ("AUTH_FAIL", 0)

        # Clear cart: go to /cart/, check all boxes, click "Usuń zaznaczone"
        log.info("[%s] Clearing cart...", email)
        await tab.get("https://www.empik.com/cart/")
        await asyncio.sleep(4)
        clear_r = await tab.evaluate("""(() => {
            // Check if cart is already empty
            if (document.body.innerText.includes('pusty')) return 'already_empty';
            // Check all checkboxes
            const cbs = document.querySelectorAll('input[type=checkbox]');
            let checked = 0;
            for (const cb of cbs) {
                if (cb.offsetParent && !cb.checked) { cb.click(); checked++; }
            }
            // Click "Usuń zaznaczone"
            const remove = document.querySelector('[data-ta="remove-selected"]');
            if (remove && remove.offsetParent) {
                remove.click();
                return 'removed:' + checked + '_checked';
            }
            return 'no_remove_btn:' + checked + '_cbs';
        })()""")
        log.info("[%s] Cart clear: %s", email, clear_r)
        await asyncio.sleep(3)
        # Confirm removal dialog if any
        await tab.evaluate("""(() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                const t = (b.textContent || '').trim().toLowerCase();
                if (b.offsetParent && (t === 'usuń' || t === 'tak' || t === 'potwierdź' || t.includes('usuń produkty'))) {
                    b.click(); return 'confirmed';
                }
            }
            return 'no_dialog';
        })()""")
        await asyncio.sleep(2)

        # Cart
        added = await add_to_cart(tab, product_url, qty)
        if added == -1:
            return ("SOLD_OUT", 0)
        if added == 0:
            return ("CART_FAIL", 0)

        # Checkout
        result = await checkout(tab, account, test_mode)
        if result in ("ORDER_PLACED", "PAYMENT_PENDING") and not test_mode:
            mark_completed(email, product_url)
            await send_discord_empik(f"\u2705 **{email}** - {result}!\nProdukt: {product_url}\nIlosc: {added}")
        return (result, added)
    except Exception as e:
        log.error("[%s] Error: %s", email, e)
        import traceback; traceback.print_exc()
        return ("ERROR", 0)
    finally:
        try: browser.stop()
        except: pass


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("product_url")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--qty", type=int, default=QUANTITY)
    parser.add_argument("--max", type=int, default=MAX_TOTAL)
    parser.add_argument("--start", type=int, default=0)
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("EMPIK BOT | qty=%d max=%d test=%s", args.qty, args.max, args.test)
    log.info("Product: %s", args.product_url)
    log.info("=" * 60)

    total = 0
    results = {}
    n = args.start if args.start > 0 else get_next_account_number(args.product_url)

    while total < args.max:
        acc = get_account(n)
        if is_completed(acc["email"], args.product_url) and not args.test:
            log.info("[%s] skip (done)", acc["email"])
            n += 1; continue

        log.info("\n>>> #%d %s (total %d/%d) <<<", n, acc["email"], total, args.max)
        result, added = await run_one(acc, args.product_url, args.qty, args.test)
        results[acc["email"]] = result

        if result == "SOLD_OUT":
            log.info("SOLD OUT -> STOP"); break
        if result in ("ORDER_PLACED", "PAYMENT_PENDING", "TEST_OK"):
            total += added
        if total >= args.max:
            log.info("MAX REACHED -> STOP"); break

        n += 1
        await asyncio.sleep(3)

    log.info("\n" + "=" * 60)
    log.info("DONE: %d items, %d accounts", total, len(results))
    # Discord summary
    summary_lines = [f"  {e}: {r}" for e, r in results.items()]
    ok_count = sum(1 for r in results.values() if r in ("ORDER_PLACED", "PAYMENT_PENDING", "TEST_OK"))
    await send_discord_empik(f"\U0001f6d2 **Empik AutoBuy** - {ok_count}/{len(results)} kont OK, {total} szt\n" + "\n".join(summary_lines[:10]))
    for e, r in results.items(): log.info("  %s: %s", e, r)

if __name__ == "__main__":
    asyncio.run(main())

