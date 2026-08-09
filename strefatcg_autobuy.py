#!/usr/bin/env python3
"""
Strefa-TCG Auto-Buy Bot
Platform: Shoper (strefa-tcg.pl)
Method: Patchright headless=False (Shoper blocks aiohttp login)
Flow: Login → Clear cart → ATC → Basket → Select BLIK → ZAMAWIAM → 
      Select paczkomat + checkboxes → PODSUMOWANIE → POTWIERDZAM ZAKUP
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
BASE_URL = "https://strefa-tcg.pl"
SHOP_NAME = "strefa-tcg"
BOT_DIR = Path("/opt/pokemon-monitor-v2")
COMPLETED_FILE = BOT_DIR / "strefatcg_completed.json"
LOG_FILE = BOT_DIR / "strefatcg_autobuy.log"
WEBHOOK_FILE = BOT_DIR / "discord_webhook_strefatcg.txt"

ACCOUNTS = [
    {"email": "esemento@gmail.com", "password": "cR!9GW#x2wqJtGw", "name": "Tomasz Szczepaniak"},
    {"email": "blackmat36@gmail.com", "password": "v2@pvDGt#ZuN3ui", "name": "Natalia Szczepaniak"},
    {"email": "tjbtaniojuzbylo@gmail.com", "password": "P9XAfQE.SCwFq5i", "name": "Jagoda Kaczmarek"},
    {"email": "y24015411@gmail.com", "password": "huw!e.twdCmv9@B", "name": "Mirosława Szczepaniak"},
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
log = logging.getLogger("strefatcg_autobuy")


def load_completed():
    if COMPLETED_FILE.exists():
        return json.loads(COMPLETED_FILE.read_text())
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


async def send_discord(message):
    """Send Discord notification."""
    try:
        if not WEBHOOK_FILE.exists():
            log.warning("No Discord webhook file")
            return
        wh_url = WEBHOOK_FILE.read_text().strip()
        if not wh_url:
            return
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(wh_url, json={"content": message})
    except Exception as e:
        log.warning(f"Discord send failed: {e}")


async def dismiss_overlay(page):
    """Remove cookie consent and fix pointer-events."""
    await page.evaluate("""
        document.querySelectorAll('.consents, .consents__mask, [class*=consent], .cookie-bar').forEach(el => el.remove());
        document.body.style.pointerEvents = 'auto';
    """)


async def login(page, email, password):
    """Login to strefa-tcg. Returns True on success."""
    for attempt in range(3):
        try:
            await page.goto(f"{BASE_URL}/pl/login", wait_until="domcontentloaded")
            await asyncio.sleep(3)
            
            # Remove overlays
            try:
                consent = page.locator('.consents__btn')
                if await consent.count() > 0:
                    await consent.first.click(timeout=3000)
                    await asyncio.sleep(1)
            except:
                pass
            await dismiss_overlay(page)
            await asyncio.sleep(0.5)
            
            # Fill form via JS (body overlay blocks PW clicks/fill)
            escaped_email = email.replace("'", "\\'")
            escaped_pass = password.replace("'", "\\'").replace("\\", "\\\\")
            await page.evaluate(f"""
                const mailEl = document.querySelector('#mail_input_long') || document.querySelector('input[name="mail"]');
                const passEl = document.querySelector('#pass_input_long') || document.querySelector('input[name="pass"]');
                if (mailEl) mailEl.value = '{escaped_email}';
                if (passEl) passEl.value = '{escaped_pass}';
            """)
            
            # Submit form
            await page.evaluate("""
                const form = document.querySelector('form[action*="/pl/login"]');
                if (form) form.submit();
            """)
            await asyncio.sleep(4)
            
            content = await page.content()
            if "wyloguj" in content.lower() or "Wyloguj" in content:
                return True
            
            log.warning(f"Login attempt {attempt+1} failed for {email}, url={page.url}")
        except Exception as e:
            log.warning(f"Login attempt {attempt+1} error: {e}")
    
    return False


async def clear_cart(page):
    """Clear cart by clicking trash icon (goto href of a.prodremove)."""
    await page.goto(f"{BASE_URL}/pl/basket", wait_until="domcontentloaded")
    await asyncio.sleep(2)
    await dismiss_overlay(page)
    
    # Check if cart has items
    has_items = await page.evaluate("() => document.body.innerText.includes('ZAMAWIAM')")
    if not has_items:
        return  # Already empty
    
    # Get href of prodremove and navigate to it (removes 1 item per visit)
    for _ in range(20):
        href = await page.evaluate("() => { const a = document.querySelector('a.prodremove'); return a ? a.href : null; }")
        if not href:
            break
        await page.goto(href, wait_until="domcontentloaded")
        await asyncio.sleep(1)
        await dismiss_overlay(page)
        # Check if empty now
        has_items = await page.evaluate("() => document.body.innerText.includes('ZAMAWIAM')")
        if not has_items:
            break


async def add_to_cart(page, product_url):
    """Go to product page and click ATC button. Returns True on success."""
    await page.goto(product_url, wait_until="domcontentloaded")
    await asyncio.sleep(2)
    await dismiss_overlay(page)
    
    # Click ATC button
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
        # Try PW locator with force
        atc = page.locator('.addtobasket, button:has-text("Do koszyka")')
        if await atc.count() > 0:
            await atc.first.click(force=True, timeout=5000)
            clicked = True
    
    if clicked:
        await asyncio.sleep(2)
        return True
    return False


async def checkout(page, test_mode=False):
    """
    Complete checkout flow by clicking through steps.
    Returns True if order placed successfully.
    """
    # === BASKET PAGE ===
    await page.goto(f"{BASE_URL}/pl/basket", wait_until="domcontentloaded")
    await asyncio.sleep(2)
    await dismiss_overlay(page)
    
    # Check if basket has items
    has_items = await page.evaluate("() => document.body.innerText.includes('ZAMAWIAM')")
    if not has_items:
        log.error("Basket is empty!")
        return False
    
    # Payment_18 (Przelewy24) is default and sufficient - user picks BLIK on P24 page
    # Just click ZAMAWIAM button to proceed to step2
    await page.evaluate("""
        () => {
            const btn = document.querySelector('button.order');
            if (btn) btn.click();
        }
    """)
    log.info("Clicked ZAMAWIAM")
    await asyncio.sleep(5)
    
    if "step2" not in page.url:
        # Check error
        body = await page.evaluate("() => document.body.innerText.substring(0, 200)")
        log.error(f"ZAMAWIAM failed, still on {page.url}: {body[:100]}")
        return False
    
    # === STEP 2: paczkomat + checkboxes ===
    log.info(f"Step 2 URL: {page.url}")
    await dismiss_overlay(page)
    await asyncio.sleep(2)
    
    # Select first paczkomat radio (name="machine")
    await page.evaluate("""
        () => {
            const machineRadios = document.querySelectorAll('input[type="radio"][name="machine"]');
            if (machineRadios.length > 0 && !Array.from(machineRadios).some(r => r.checked)) {
                machineRadios[0].checked = true;
                machineRadios[0].dispatchEvent(new Event('change', {bubbles: true}));
            }
        }
    """)
    await asyncio.sleep(1)
    
    # Check ALL checkboxes
    await page.evaluate("""
        () => {
            document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                if (!cb.checked) {
                    cb.checked = true;
                    cb.dispatchEvent(new Event('change', {bubbles: true}));
                }
            });
        }
    """)
    await asyncio.sleep(1)
    
    # Click PODSUMOWANIE
    await page.evaluate("""
        () => {
            const btn = Array.from(document.querySelectorAll('a, button, input[type="submit"]'))
                .find(el => (el.innerText || el.value || '').includes('PODSUMOWANIE'));
            if (btn) btn.click();
        }
    """)
    log.info("Clicked PODSUMOWANIE")
    await asyncio.sleep(4)
    
    if "step3" not in page.url:
        log.error(f"PODSUMOWANIE failed, on {page.url}")
        return False
    
    # === STEP 3: Confirmation ===
    if test_mode:
        confirm = page.locator('button:has-text("POTWIERDZAM")')
        found = await confirm.count()
        log.info(f"[TEST MODE] POTWIERDZAM button found: {found > 0}")
        if found:
            # Submit to verify payment redirect
            await page.evaluate("() => { const btn = document.querySelector('button.order'); if(btn) btn.click(); }")
            log.info("[TEST MODE] Clicked POTWIERDZAM!")
            await asyncio.sleep(8)
            url = page.url
            log.info(f"[TEST MODE] After submit URL: {url}")
            if "przelewy24" in url or "pay" in url or "blik" in url or "basket" not in url:
                log.info("[TEST MODE] PAYMENT PAGE REACHED! ✅")
                return True
            else:
                body = await page.evaluate("() => document.body.innerText.substring(0, 200)")
                log.warning(f"[TEST MODE] Didn't reach payment: {body[:100]}")
                return False
        else:
            return False
    
    # REAL MODE - click confirm
    confirm = page.locator('button:has-text("POTWIERDZAM")')
    if await confirm.count() > 0:
        await page.evaluate("() => { const btn = document.querySelector('button.order'); if(btn) btn.click(); }")
        log.info("Clicked POTWIERDZAM ZAKUP!")
        await asyncio.sleep(8)
        
        url = page.url
        if "przelewy24" in url or "pay" in url or "blik" in url or "basket" not in url:
            log.info(f"Payment page reached! URL: {url}")
            return True
        else:
            body = await page.evaluate("() => document.body.innerText.substring(0, 200)")
            log.warning(f"After confirm: {body[:100]}")
            return False
    else:
        log.error("POTWIERDZAM button not found!")
        return False


async def logout(page):
    """Logout from strefa-tcg."""
    try:
        await page.goto(f"{BASE_URL}/pl/logout", wait_until="domcontentloaded")
        await asyncio.sleep(2)
    except:
        pass



async def run_for_account_batch(page, account, product_urls, test_mode=False):
    """Run full buy flow for one account with MULTIPLE products in one cart."""
    email = account["email"]
    name = account["name"]
    
    # Filter out already completed products
    urls_to_buy = []
    for url in product_urls:
        pid_match = re.search(r'/(\d+)$', url)
        pid = pid_match.group(1) if pid_match else url.split("/")[-1]
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
        await logout(page)
        return "atc_failed"
    
    log.info(f"[{name}] {added}/{len(urls_to_buy)} products in cart")
    
    # Checkout (all products in one order)
    ok = await checkout(page, test_mode=test_mode)
    if ok:
        log.info(f"[{name}] ORDER PLACED! ({added} products)")
        if not test_mode:
            # Mark all added products as completed
            for url in urls_to_buy:
                pid_match = re.search(r'/(\d+)$', url)
                pid = pid_match.group(1) if pid_match else url.split("/")[-1]
                mark_completed(pid, email)
            await send_discord(f"✅ **{name}** - zamówienie złożone! ({added} produktów)\n💳 Zapłać BLIK na stronie płatności")
        return "success"
    else:
        log.error(f"[{name}] Checkout FAILED")
        await logout(page)
        return "checkout_failed"


async def main():
    parser = argparse.ArgumentParser(description="Strefa-TCG Auto-Buy Bot")
    parser.add_argument("product_urls", nargs="+", help="Product URL(s) to buy")
    parser.add_argument("--test", action="store_true", help="Test mode (don't confirm order)")
    parser.add_argument("--accounts", type=int, default=4, help="Number of accounts (1-4)")
    parser.add_argument("--qty", type=int, default=1, help="Quantity per product per account")
    parser.add_argument("--start", type=int, default=1, help="Start from account N")
    args = parser.parse_args()
    
    product_urls = args.product_urls
    
    accounts_to_use = ACCOUNTS[:args.accounts]
    if args.test:
        accounts_to_use = [TEST_ACCOUNT]
        log.info("=== TEST MODE (using test account) ===")
    
    log.info(f"Products ({len(product_urls)}):")
    for url in product_urls:
        log.info(f"  {url}")
    log.info(f"Accounts: {len(accounts_to_use)}, Qty: {args.qty}")
    log.info(f"Test mode: {args.test}")
    
    # Notify Discord
    if not args.test:
        prod_list = "\n".join([f"• {url.split('/')[-2][:50]}" for url in product_urls])
        await send_discord(f"🚨 **STREFA-TCG AutoBuy** uruchomiony!\n{prod_list}\nKonta: {len(accounts_to_use)}")
    
    results = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox'],
            proxy={"server": "http://127.0.0.1:8888"},
        )
        
        for i, account in enumerate(accounts_to_use):
            if i < args.start - 1:
                continue
            
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
            page = await ctx.new_page()
            
            try:
                # Build list of URLs × qty
                all_urls = []
                for url in product_urls:
                    for _ in range(args.qty):
                        all_urls.append(url)
                
                result = await run_for_account_batch(page, account, all_urls, test_mode=args.test)
                results.append((account["name"], result))
            except Exception as e:
                log.error(f"[{account['name']}] Exception: {e}")
                results.append((account["name"], f"error: {e}"))
            finally:
                await ctx.close()
            
            # Small delay between accounts
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
    
    # Discord summary
    if not args.test:
        lines = [f"🛒 **Strefa-TCG AutoBuy** - {success_count}/{len(results)} zamówień!"]
        for name, result in results:
            icon = "✅" if result == "success" else "❌"
            lines.append(f"{icon} {name}: {result}")
        await send_discord("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
