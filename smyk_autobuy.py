#!/usr/bin/env python3
"""SMYK Auto-Buy Bot v2 - with cart clearing and test mode"""
import asyncio, sys, os, logging
from bot_utils import wait_for_verification
from bot_engine import BotEngine
_engine = BotEngine(shop="smyk")

ACCOUNTS = [
    {"email":"esemento@gmail.com","password":"cR!9GW#x2wqJtGw","firstName":"Tomasz","lastName":"Szczepaniak","street":"Lesna","streetNumber":"46a","flatNumber":"2","zipCode":"62-069","city":"Paledzie","phone":"607183797"},
    {"email":"blackmat36@gmail.com","password":"v2@pvDGt#ZuN3ui","firstName":"Natalia","lastName":"Szczepaniak","street":"Zgoda","streetNumber":"30b","flatNumber":"","zipCode":"60-122","city":"Poznan","phone":"514635586"},
    {"email":"tjbtaniojuzbylo@gmail.com","password":"P9XAfQE.SCwFq5i","firstName":"Jagoda","lastName":"Kaczmarek","street":"Bukowska","streetNumber":"104a","flatNumber":"7","zipCode":"60-397","city":"Poznan","phone":"535024946"},
    {"email":"y24015411@gmail.com","password":"huw!e.twdCmv9@B","firstName":"Miroslawa","lastName":"Szczepaniak","street":"Bukowska","streetNumber":"104a","flatNumber":"7","zipCode":"60-397","city":"Poznan","phone":"603466903"},
]

QUANTITY = 12
DISCORD_WEBHOOK = ""
_wh_path = "/opt/pokemon-monitor-v2/discord_webhook_smyk.txt"
if os.path.exists(_wh_path):
    DISCORD_WEBHOOK = open(_wh_path).read().strip()
LOG_FILE = "/opt/pokemon-monitor-v2/smyk_autobuy.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SMYK-BOT] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, mode='a')
    ]
)
log = logging.getLogger(__name__)


async def send_discord(msg):
    if not DISCORD_WEBHOOK:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(DISCORD_WEBHOOK, json={"content": msg})
    except Exception:
        pass


async def clear_cart(pg, nm):
    """Go to cart and remove all items."""
    log.info(f"[{nm}] Clearing cart...")
    await pg.goto("https://www.smyk.com/pl/pl/koszyk", wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(4)

    # Check if cart is empty
    empty_indicators = ["Twój koszyk jest pusty", "koszyk jest pusty", "Koszyk jest pusty"]
    page_text = await pg.inner_text("body")
    for indicator in empty_indicators:
        if indicator in page_text:
            log.info(f"[{nm}] Cart already empty")
            return True

    # Try to remove all items - look for remove/trash buttons
    removed = 0
    for attempt in range(20):  # max 20 items
        try:
            # Common remove button selectors for smyk
            remove_btn = None
            for selector in [
                "button[aria-label*='suń']",
                "button[aria-label*='Usuń']",
                "[data-testid*='remove']",
                "[data-testid*='delete']",
                "button:has(svg[data-testid*='trash'])",
                ".cart-item__remove",
                "button:has-text('Usuń')",
                "[aria-label*='remove']",
                "[aria-label*='delete']",
                "button[class*='remove']",
                "button[class*='delete']",
            ]:
                loc = pg.locator(selector)
                if await loc.count() > 0:
                    remove_btn = loc.first
                    break

            if not remove_btn:
                # Try JS approach - find trash/remove icons
                found = await pg.evaluate("""() => {
                    var btns = document.querySelectorAll('button, [role=button]');
                    for (var b of btns) {
                        var txt = (b.innerText || '').toLowerCase();
                        var lbl = (b.getAttribute('aria-label') || '').toLowerCase();
                        if (txt.includes('usuń') || lbl.includes('usuń') || lbl.includes('remove') || lbl.includes('delete')) {
                            b.click();
                            return true;
                        }
                    }
                    var svgs = document.querySelectorAll('button svg, [role=button] svg');
                    for (var s of svgs) {
                        var parent = s.closest('button') || s.closest('[role=button]');
                        if (parent && !(parent.innerText || '').trim()) {
                            parent.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                if not found:
                    break
                await asyncio.sleep(3)
                removed += 1
                continue

            await remove_btn.click()
            await asyncio.sleep(3)
            removed += 1
        except Exception as e:
            log.info(f"[{nm}] Remove attempt {attempt}: {e}")
            break

    # Confirm deletion if dialog appears
    try:
        confirm = pg.locator("button:has-text('Potwierdź'), button:has-text('Tak'), button:has-text('OK')")
        if await confirm.count() > 0:
            await confirm.first.click()
            await asyncio.sleep(2)
    except:
        pass

    if removed > 0:
        log.info(f"[{nm}] Removed {removed} items from cart")
    else:
        # Maybe cart was empty after all or selectors didn't match
        log.info(f"[{nm}] No items removed (cart may be empty or selectors need update)")

    # Verify cart is empty
    await pg.reload(wait_until="domcontentloaded")
    await asyncio.sleep(3)
    page_text = await pg.inner_text("body")
    for indicator in empty_indicators:
        if indicator in page_text:
            log.info(f"[{nm}] Cart confirmed empty")
            return True

    log.warning(f"[{nm}] Cart may not be fully empty - proceeding anyway")
    return True


async def add_to_cart(pg, url, nm):
    """Navigate to product and add QUANTITY times."""
    log.info(f"[{nm}] Adding product {QUANTITY}x: {url}")
    await pg.goto(url, wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(4)

    # Dismiss cookies popup (blocks clicks)
    await dismiss_cookies(pg)
    # Also force-remove any overlays via JS
    await pg.evaluate("""() => {
        document.querySelectorAll('[class*=cookies-policy], [class*=cookie-popup], .fixed-background, [data-testid=fixed-background]').forEach(e => e.remove());
    }""")
    await asyncio.sleep(1)

    btn = pg.locator(".btn--with-action:has-text('Dodaj do koszyka')")
    try:
        await btn.first.wait_for(timeout=15000)
    except:
        log.error(f"[{nm}] 'Dodaj do koszyka' button NOT FOUND!")
        return 0

    added = 0
    consecutive_fails = 0
    for i in range(QUANTITY):
        try:
            # Remove any blocking overlays before each click
            await pg.evaluate("""() => {
                document.querySelectorAll('[class*=cookies-policy], .fixed-background, [data-testid=fixed-background], [class*=overlay]:not([class*=product])').forEach(e => e.remove());
            }""")
            await btn.first.click(timeout=10000)
            await asyncio.sleep(2.5)
            # Dismiss overlay/popup if appears after adding
            try:
                ov = pg.locator("[data-testid='fixed-background']")
                if await ov.is_visible(timeout=1500):
                    await ov.click()
                    await asyncio.sleep(1)
            except:
                pass
            added += 1
            consecutive_fails = 0
            log.info(f"[{nm}] Added {added}/{QUANTITY}")
        except Exception as e:
            consecutive_fails += 1
            log.warning(f"[{nm}] Add attempt {i+1} failed: {e}")
            if consecutive_fails >= 3:
                log.warning(f"[{nm}] 3 consecutive fails, likely reached limit")
                break
            # Refresh and retry
            await pg.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(4)
            await dismiss_cookies(pg)
            await pg.evaluate("""() => {
                document.querySelectorAll('[class*=cookies-policy], .fixed-background').forEach(e => e.remove());
            }""")
            btn = pg.locator(".btn--with-action:has-text('Dodaj do koszyka')")
            try:
                await btn.first.wait_for(timeout=10000)
            except:
                log.error(f"[{nm}] Button gone after refresh, stopping at {added}")
                break

    log.info(f"[{nm}] Total added: {added}")
    return added


async def checkout(pg, acc, nm, test_mode=False):
    """Process checkout: delivery, payment, order."""
    log.info(f"[{nm}] Going to checkout...")
    await pg.goto("https://www.smyk.com/pl/pl/koszyk/dostawa-i-platnosc", wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(10)

    # Accept cookies/terms if prompted
    try:
        accept_btn = pg.locator(".btn--with-action:has-text('Akceptuj'), button:has-text('Akceptuj')")
        if await accept_btn.count() > 0:
            await accept_btn.first.click(timeout=3000)
            await asyncio.sleep(2)
    except:
        pass

    # Remove any overlays blocking the page
    await pg.evaluate("""() => {
        document.querySelectorAll('.fixed-background, [class*=overlay], [data-testid=fixed-background]').forEach(e => e.remove());
        var h = document.querySelector('header.fixed, header[class*=fixed]');
        if (h) h.style.position = 'relative';
    }""")
    await asyncio.sleep(1)

    # --- FILL ADDRESS if needed ---
    for fn in ["firstName", "lastName", "street", "streetNumber", "flatNumber", "zipCode", "city", "phone"]:
        v = acc.get(fn, "")
        if not v:
            continue
        try:
            f = pg.locator(f"input[name='{fn}']").first
            if await f.is_visible(timeout=2000):
                current_val = await f.input_value()
                if not current_val.strip():
                    await f.fill(v)
                    await asyncio.sleep(0.5)
        except:
            pass
    log.info(f"[{nm}] Address fields checked/filled")
    await asyncio.sleep(3)

    # --- SELECT DELIVERY (DPD/Kurier) if not selected ---
    log.info(f"[{nm}] Checking delivery...")
    await pg.evaluate("""() => {
        var radios = document.querySelectorAll('input[type=radio]');
        var anyChecked = false;
        for (var r of radios) {
            var container = r.closest('label') || r.closest('div');
            if (!container) continue;
            var text = container.innerText || '';
            if ((text.includes('DPD') || text.includes('Kurier') || text.includes('kurier')) && r.checked) {
                anyChecked = true;
                break;
            }
        }
        if (!anyChecked) {
            // Try to select DPD/Kurier
            for (var r of radios) {
                var container = r.closest('label') || r.closest('div');
                if (!container) continue;
                var text = container.innerText || '';
                if (text.includes('DPD') || text.includes('Kurier') || text.includes('kurier')) {
                    r.click();
                    r.dispatchEvent(new Event('change', {bubbles: true}));
                    break;
                }
            }
        }
    }""")
    await asyncio.sleep(5)
    log.info(f"[{nm}] Delivery selected")

    # --- SELECT BLIK payment if not selected ---
    log.info(f"[{nm}] Checking payment method...")
    await pg.evaluate("""() => {
        // Check if BLIK is already selected
        var blikInput = document.querySelector('input[name=blik]');
        if (blikInput && blikInput.offsetParent) return; // BLIK field visible = already selected

        var radios = document.querySelectorAll('input[name=payment][type=radio], input[type=radio]');
        for (var r of radios) {
            var container = r.closest('label') || r.closest('div');
            if (!container) continue;
            var text = container.innerText || '';
            if (text.includes('BLIK') || text.includes('Blik') || text.includes('blik')) {
                if (!r.checked) {
                    r.click();
                    r.dispatchEvent(new Event('change', {bubbles: true}));
                }
                break;
            }
        }
    }""")
    await asyncio.sleep(4)
    log.info(f"[{nm}] BLIK payment selected")

    # Remove overlays again before final steps
    await pg.evaluate("""() => {
        document.querySelectorAll('.fixed-background, [class*=overlay]').forEach(e => e.remove());
    }""")
    await asyncio.sleep(1)

    # === TEST MODE: Stop here ===
    if test_mode:
        # Verify we can see BLIK input and order button
        blik_visible = await pg.locator("input[name='blik']").count() > 0
        order_btn = await pg.locator("[aria-label='Zamów i zapłać']").count() > 0

        log.info(f"[{nm}] === TEST MODE RESULTS ===")
        log.info(f"[{nm}] BLIK input visible: {blik_visible}")
        log.info(f"[{nm}] Order button visible: {order_btn}")
        log.info(f"[{nm}] Current URL: {pg.url}")

        # Take screenshot info
        page_text = await pg.inner_text("body")
        has_delivery = "DPD" in page_text or "Kurier" in page_text or "dostaw" in page_text.lower()
        has_blik = "BLIK" in page_text or "Blik" in page_text
        log.info(f"[{nm}] Page has delivery info: {has_delivery}")
        log.info(f"[{nm}] Page has BLIK info: {has_blik}")

        if blik_visible and order_btn:
            log.info(f"[{nm}] TEST PASSED - Ready to order!")
            await send_discord(f"[{nm}] TEST OK - gotowy do zamowienia")
            return "TEST_PASSED"
        else:
            log.error(f"[{nm}] TEST FAILED - missing elements")
            await send_discord(f"[{nm}] TEST FAILED")
            return "TEST_FAILED"

    # === PRODUCTION MODE: Enter BLIK and order ===
    blik = pg.locator("input[name='blik']")
    if await blik.count() > 0:
        await blik.first.fill("654654")
        log.info(f"[{nm}] BLIK code entered")
    else:
        log.error(f"[{nm}] BLIK input NOT FOUND!")
        return False
    await asyncio.sleep(2)

    # Click order button
    order_btn = pg.locator("[aria-label='Zamów i zapłać']")
    if await order_btn.count() == 0:
        log.error(f"[{nm}] Order button NOT FOUND!")
        return False

    await order_btn.first.scroll_into_view_if_needed()
    await asyncio.sleep(1)
    await order_btn.first.click()
    log.info(f"[{nm}] Clicked 'Zamów i zapłać'")

    # Wait for confirmation
    await asyncio.sleep(20)
    if "potwierdzenie" in pg.url.lower():
        log.info(f"[{nm}] ORDER PLACED! {pg.url}")
        await send_discord(f"[{nm}] ZAMOWIONE! {pg.url}")
        return True
    else:
        log.error(f"[{nm}] Order may have failed. URL: {pg.url}")
        page_text = await pg.inner_text("body")
        if "błąd" in page_text.lower() or "error" in page_text.lower():
            log.error(f"[{nm}] Error on page detected")
        await send_discord(f"[{nm}] FAILED - URL: {pg.url}")
        return False


async def dismiss_cookies(pg):
    """Dismiss cookie popup if present."""
    try:
        for sel in [
            "button:has-text('Akceptuję')",
            "button:has-text('Akceptuj')",
            ".cookies-policy-popup button",
            "[class*='cookie'] button:has-text('Akceptuj')",
            "[class*='cookie'] button:has-text('OK')",
        ]:
            loc = pg.locator(sel)
            if await loc.count() > 0 and await loc.first.is_visible(timeout=2000):
                await loc.first.click()
                await asyncio.sleep(2)
                return True
    except:
        pass
    # Fallback: remove popup via JS
    await pg.evaluate("""() => {
        document.querySelectorAll('[class*=cookies-policy], [class*=cookie-popup], [class*=cookie-consent]').forEach(e => e.remove());
    }""")
    return False


async def buy_one(acc, url, p, test_mode=False):
    """Full flow for one account: login -> clear cart -> add -> checkout."""
    nm = f"{acc['firstName']} ({acc['email'][:8]})"
    log.info(f"[{nm}] === START {'(TEST MODE)' if test_mode else '(PRODUCTION)'} ===")
    b = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"], proxy=_engine.get_proxy(acc["email"]) or {"server": "http://127.0.0.1:8888"})
    fp = _engine.get_fingerprint(ACCOUNTS.index(acc) if acc in ACCOUNTS else 0)
    ctx = await b.new_context(viewport=fp["viewport"], user_agent=fp["user_agent"])
    pg = await ctx.new_page()
    try:
        # --- LOGIN ---
        log.info(f"[{nm}] Logging in...")
        await pg.goto("https://www.smyk.com/pl/pl/login", wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_selector("input#username", timeout=15000)
        await asyncio.sleep(2)
        # Dismiss cookies before login
        await dismiss_cookies(pg)
        await pg.fill("input#username", acc["email"])
        await pg.fill("input#password", acc["password"])
        await pg.locator(".btn--with-action:has-text('Zaloguj')").first.click()
        await asyncio.sleep(6)

        if "/login" in pg.url:
            log.error(f"[{nm}] LOGIN FAILED! Still on login page.")
            return False
        log.info(f"[{nm}] Logged in OK")

        # --- CLEAR CART ---
        await clear_cart(pg, nm)

        # --- ADD TO CART ---
        added = await add_to_cart(pg, url, nm)
        if added == 0:
            log.error(f"[{nm}] Could not add any items!")
            return False

        # --- CHECKOUT ---
        result = await checkout(pg, acc, nm, test_mode=test_mode)
        return result

    except Exception as e:
        log.error(f"[{nm}] EXCEPTION: {e}")
        import traceback
        log.error(traceback.format_exc())
        return False
    finally:
        await b.close()


async def autobuy_all(url, test_mode=False):
    from playwright.async_api import async_playwright

    mode_str = "TEST" if test_mode else "PRODUCTION"
    log.info(f"=== SMYK BOT {mode_str} MODE - {url} ===")
    await send_discord(f"SMYK BOT [{mode_str}] Starting 4 accounts: {url}")

    results = {}
    async with async_playwright() as p:
        for acc in ACCOUNTS:
            nm = f"{acc['firstName']} ({acc['email'][:8]})"
            result = await buy_one(acc, url, p, test_mode=test_mode)
            results[nm] = result
            await asyncio.sleep(2)  # Small pause between accounts

    # Summary
    log.info("=== RESULTS SUMMARY ===")
    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        if result == "TEST_PASSED":
            status = "TEST OK"
        elif result == "TEST_FAILED":
            status = "TEST FAIL"
        log.info(f"  {name}: {status}")

    await send_discord(f"SMYK BOT [{mode_str}] Done: " + ", ".join(f"{n}={'OK' if r else 'FAIL'}" for n, r in results.items()))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 smyk_autobuy.py [--test] <product_url>")
        print("  --test  = go through entire flow WITHOUT entering BLIK code")
        print("  (no flag) = FULL buy with BLIK code 654654")
        sys.exit(1)

    test_mode = "--test" in sys.argv
    url = [a for a in sys.argv[1:] if a != "--test"][0]

    log.info(f"URL: {url}")
    log.info(f"Mode: {'TEST' if test_mode else 'PRODUCTION'}")

    asyncio.run(autobuy_all(url, test_mode=test_mode))
