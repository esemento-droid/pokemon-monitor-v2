#!/usr/bin/env python3
"""
JC Torpedo Daemon — persistent browser, pre-logged accounts, instant checkout.

Architecture:
  - 1 patchright browser (stealth, mobile proxy) — ALWAYS running
  - 4 pages (tabs) — one per account, PRE-LOGGED IN
  - On trigger: goto /cart/add/{id} → click checkout → submit = ~6s
  - Session refresh every 50 min (keep cookies alive)
  - Trigger via file: write product_id to /tmp/jc_torpedo_fire.txt

Usage:
  # Start daemon (systemd or manual):
  DISPLAY=:99 ./venv/bin/python3 jc_torpedo_daemon.py

  # Fire torpedo (from trigger):
  echo "7437" > /tmp/jc_torpedo_fire.txt

  # Or direct fire (bypasses daemon, uses own browser):
  DISPLAY=:99 ./venv/bin/python3 jc_torpedo_daemon.py --fire 7437
"""
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path("/opt/pokemon-monitor-v2")
FIRE_FILE = Path("/tmp/jc_torpedo_fire.txt")
COMPLETED_FILE = BASE_DIR / "japancollectibles_completed.json"
LOG_FILE = BASE_DIR / "jc_torpedo_daemon.log"
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
PROXY = {"server": "http://127.0.0.1:8888"}

SESSION_REFRESH = 3000  # 50 min


class TorpedoDaemon:
    def __init__(self, accounts):
        self.accounts = accounts
        self.browser = None
        self.context = None
        self.pages = {}  # email -> page
        self.last_login = {}  # email -> timestamp
        self._pw = None

    async def start(self):
        """Start browser and login all accounts."""
        from patchright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
            proxy=PROXY,
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=UA,
        )
        log.info("[DAEMON] Browser started (patchright stealth + proxy)")

        # Login all accounts
        for account in self.accounts:
            await self._login_account(account)
            await asyncio.sleep(2)

        log.info(f"[DAEMON] All {len(self.pages)} accounts ready. Waiting for trigger...")

    async def _login_account(self, account):
        """Login one account on a dedicated page."""
        email = account["email"]
        page = await self.context.new_page()

        try:
            # Navigate to login
            await page.goto(f"{SHOP_URL}/login", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)

            # Dismiss age gate + overlays
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.getElementById('cm')?.remove();
                document.querySelector('.fixed-elements')?.remove();
                const ageBtn = document.querySelector('.skyshop-alert-conditional-access button');
                if (ageBtn) ageBtn.click();
            }""")
            await page.wait_for_timeout(1000)

            # Fill login form
            await page.fill("input#email", email, timeout=5000)
            await page.fill("input[name='password']", account["password"], timeout=5000)
            await page.click("button[name='submit']", force=True)
            await page.wait_for_timeout(3000)

            # Verify
            content = await page.content()
            if "Moje konto" in content:
                self.pages[email] = page
                self.last_login[email] = time.time()
                log.info(f"[DAEMON] [{email}] Logged in ✓")
            else:
                log.error(f"[DAEMON] [{email}] Login FAILED")
                await page.close()
        except Exception as e:
            log.error(f"[DAEMON] [{email}] Login error: {e}")
            await page.close()

    async def _refresh_session(self, account):
        """Re-login stale session."""
        email = account["email"]
        if email in self.pages:
            try:
                await self.pages[email].close()
            except:
                pass
            del self.pages[email]
        await self._login_account(account)

    async def fire(self, product_id):
        """
        FIRE TORPEDO — buy product on all logged-in accounts.
        This is the hot path. Every millisecond counts.
        """
        t0 = time.time()
        log.info(f"=== 🚀 TORPEDO FIRE product={product_id} ===")
        await self._send_discord(f"🚀 **TORPEDO FIRE** product {product_id}")

        # Fire all accounts in PARALLEL
        tasks = [self._buy_one(email, product_id, t0) for email in self.pages]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        total = time.time() - t0
        ok = sum(1 for r in results if r is True)
        log.info(f"=== TORPEDO DONE: {ok}/{len(tasks)} in {total:.1f}s ===")

        status = "✅" if ok > 0 else "❌"
        await self._send_discord(f"{status} **TORPEDO** product {product_id} | {ok}/{len(tasks)} | {total:.1f}s")
        return ok

    async def _buy_one(self, email, product_id, t0):
        """Buy on one pre-logged account page. Target: ~6s."""
        page = self.pages.get(email)
        if not page:
            log.error(f"[{email}] No page (not logged in)")
            return False

        try:
            # === STEP 1: ATC — go to product page and click "Do koszyka" ===
            product_url = f"{SHOP_URL}/Pokemon-TCG-Angielski-Mega-Heroes-Mini-Tin-p{product_id}" if not product_id.startswith("http") else product_id
            # Generic URL that works for any product ID
            product_url = f"{SHOP_URL}/-p{product_id}"
            await page.goto(product_url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)

            # Dismiss overlays
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.getElementById('cm')?.remove();
                document.querySelector('.fixed-elements')?.remove();
                document.querySelector('.skyshop-alert-conditional-access')?.remove();
            }""")

            # Click "Do koszyka" button
            try:
                atc_btn = page.locator("button:has-text('Do koszyka'), button:has-text('Dodaj do koszyka')").first
                await atc_btn.wait_for(state="visible", timeout=8000)
                await atc_btn.click(force=True)
                log.info(f"[{email}] ATC click OK ({time.time()-t0:.1f}s)")
            except Exception as e:
                log.error(f"[{email}] ATC button not found: {e}")
                return False

            await page.wait_for_timeout(2000)

            # Go to cart
            await page.goto(f"{SHOP_URL}/cart/", wait_until="domcontentloaded", timeout=10000)
            log.info(f"[{email}] Cart page ({time.time()-t0:.1f}s)")

            # === STEP 2: Wait for cart to load, then click "Przejdź do kasy" ===
            # Wait for Angular to hydrate cart (product appears)
            for _ in range(20):
                cart_ready = await page.evaluate("""() => {
                    const text = document.body.innerText;
                    const hasProduct = !text.includes('Koszyk jest pusty') && 
                                       text.includes('Suma') && !text.includes('0,00 zł');
                    const btn = document.querySelector('button[data-ng-click="order()"]');
                    return hasProduct || (btn && !btn.disabled);
                }""")
                if cart_ready:
                    break
                await page.wait_for_timeout(500)

            log.info(f"[{email}] Cart hydrated ({time.time()-t0:.1f}s)")

            # Click "Przejdź do kasy"
            try:
                order_btn = page.locator('button[data-ng-click="order()"]:not([disabled])').first
                await order_btn.wait_for(state="visible", timeout=10000)
                await order_btn.click()
            except:
                # Fallback: force Angular scope
                await page.evaluate("""() => {
                    const btn = document.querySelector('button[data-ng-click="order()"]');
                    if (btn && !btn.disabled) btn.click();
                }""")

            log.info(f"[{email}] Checkout click ({time.time()-t0:.1f}s)")

            # === STEP 3: Wait for checkout render ===
            # After click, Sky-Shop navigates to /order (full page or Angular route)
            # Wait for URL to change to /order OR for payment radios to appear
            for _ in range(30):
                state = await page.evaluate("""() => {
                    const url = window.location.href;
                    const radios = document.querySelectorAll('input[type="radio"]');
                    const hasPayment = document.body.innerText.includes('BLIK') && radios.length > 0;
                    return {url, radios: radios.length, hasPayment};
                }""")
                if state.get('hasPayment') or '/order' in state.get('url', ''):
                    break
                await page.wait_for_timeout(500)

            log.info(f"[{email}] Checkout rendered ({time.time()-t0:.1f}s)")

            # === DEBUG: full DOM analysis of checkout ===
            debug_dom = await page.evaluate("""() => {
                const text = document.body.innerText;
                // Find BLIK in DOM — what element is it?
                const allEls = document.querySelectorAll('*');
                let blikEl = null;
                let blikInfo = 'not_found';
                for (const el of allEls) {
                    if (el.childNodes.length <= 3 && el.textContent.trim() === 'BLIK') {
                        blikEl = el;
                        blikInfo = {tag: el.tagName, class: el.className.substring(0,80), parent: el.parentElement?.tagName + '.' + el.parentElement?.className.substring(0,50), ngClick: el.getAttribute('data-ng-click') || el.parentElement?.getAttribute('data-ng-click') || 'none'};
                        break;
                    }
                }
                // Find all clickable elements in order/checkout section
                const orderSection = document.querySelector('[data-ng-controller*="Order"], .order, .checkout, [class*="order"]');
                const orderInfo = orderSection ? {tag: orderSection.tagName, class: orderSection.className.substring(0,60), childCount: orderSection.children.length} : 'no_order_section';
                // Find radio-like elements (md-radio, custom)
                const mdRadios = document.querySelectorAll('md-radio-button, [role="radio"], .radio, [data-ng-click*="set"]');
                const mdInfo = [...mdRadios].slice(0,8).map(r => ({tag: r.tagName, text: r.textContent.trim().substring(0,30), ngClick: r.getAttribute('data-ng-click')?.substring(0,60) || 'none', class: r.className.substring(0,40)}));
                // Standard inputs
                const inputs = document.querySelectorAll('input');
                const inputInfo = [...inputs].slice(0,10).map(i => ({type: i.type, name: i.name, id: i.id}));
                return {blikInfo, orderInfo, mdRadios: mdInfo.length, mdDetails: mdInfo, inputs: inputInfo, url: window.location.href, hasOrder: text.includes('Zamawiam')};
            }""")
            log.info(f"[{email}] DOM ANALYSIS: {json.dumps(debug_dom, ensure_ascii=False, default=str)}")

            # === STEP 4: Select payment (BLIK) ===
            pay_result = await page.evaluate("""() => {
                const rows = document.querySelectorAll('tr, div, label, li, span');
                for (const r of rows) {
                    if (r.textContent.includes('BLIK')) {
                        const radio = r.querySelector('input[type="radio"]') || r.closest('label')?.querySelector('input[type="radio"]');
                        if (radio) { radio.click(); return 'blik_radio'; }
                        r.click(); return 'blik_click';
                    }
                }
                // Fallback: first radio
                const radio = document.querySelector('input[type="radio"]');
                if (radio) { radio.click(); return 'first_radio: ' + radio.name + '=' + radio.value; }
                return 'none';
            }""")
            log.info(f"[{email}] Payment: {pay_result}")

            await page.wait_for_timeout(2000)  # Delivery loads after payment

            # === STEP 5: Select delivery (Kurier Inpost) ===
            del_result = await page.evaluate("""() => {
                const rows = document.querySelectorAll('tr, div, label, li, span');
                for (const r of rows) {
                    if ((r.textContent.includes('Kurier') && r.textContent.includes('Inpost')) || r.textContent.includes('Gabaryt')) {
                        const radio = r.querySelector('input[type="radio"]') || r.closest('label')?.querySelector('input[type="radio"]');
                        if (radio) { radio.click(); return 'kurier_radio'; }
                        r.click(); return 'kurier_click';
                    }
                }
                // Fallback: find delivery radio (skip payment ones)
                const allRadios = [...document.querySelectorAll('input[type="radio"]')];
                const deliveryRadio = allRadios.find(r => {
                    const section = r.closest('[class*="shipment"], [class*="delivery"], [data-ng-repeat*="shipment"]');
                    return section !== null;
                });
                if (deliveryRadio) { deliveryRadio.click(); return 'fallback_delivery'; }
                return 'none';
            }""")
            log.info(f"[{email}] Delivery: {del_result}")

            await page.wait_for_timeout(1000)

            # === STEP 6: Check ALL checkboxes ===
            cb_result = await page.evaluate("""() => {
                window.scrollTo(0, document.body.scrollHeight);
                let count = 0;
                document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                    if (!cb.checked) { cb.click(); count++; }
                });
                return count;
            }""")
            log.info(f"[{email}] Checkboxes: {cb_result} clicked")

            await page.wait_for_timeout(500)

            # === DEBUG: dump state before submit ===
            debug = await page.evaluate("""() => {
                const radios = [...document.querySelectorAll('input[type="radio"]:checked')];
                const cbs = [...document.querySelectorAll('input[type="checkbox"]:checked')];
                const btn = document.querySelector('button[name="finish"]');
                return {
                    checked_radios: radios.map(r => r.name + '=' + r.value + ' id=' + r.id),
                    checked_checkboxes: cbs.length,
                    submit_btn: btn ? {disabled: btn.disabled, text: btn.textContent.trim().substring(0,30)} : 'NOT FOUND',
                    url: window.location.href
                };
            }""")
            log.info(f"[{email}] PRE-SUBMIT state: {debug}")

            # === STEP 7: Submit order ===
            log.info(f"[{email}] Submitting ({time.time()-t0:.1f}s)")
            await page.evaluate("""() => {
                const btn = document.querySelector('button[name="finish"]') || 
                            document.querySelector('button[type="submit"]');
                if (btn) btn.click();
            }""")

            await page.wait_for_timeout(5000)
            final_url = page.url
            total = time.time() - t0

            # Check result
            success = any(kw in final_url.lower() for kw in ["potwierdzenie", "thank", "tpay", "blik", "przelewy24"])
            if not success:
                content = await page.content()
                success = any(kw in content.lower() for kw in ["zamówienie zostało złożone", "dziękujemy", "potwierdzenie zamówienia"])

            if success:
                log.info(f"[{email}] ✅ ORDER in {total:.1f}s! → {final_url}")
                _mark_completed(product_id, email)
                return True
            else:
                log.error(f"[{email}] ❌ Failed ({total:.1f}s) URL: {final_url}")
                await page.screenshot(path=f"/tmp/jc_torpedo_{email.split('@')[0]}.png")
                return False

        except Exception as e:
            log.error(f"[{email}] Exception: {e}")
            return False

    async def run_daemon(self):
        """Main daemon loop: watch for trigger file + refresh sessions."""
        while True:
            # Check trigger file
            if FIRE_FILE.exists():
                try:
                    product_id = FIRE_FILE.read_text().strip()
                    FIRE_FILE.unlink()
                    if product_id:
                        await self.fire(product_id)
                except Exception as e:
                    log.error(f"[DAEMON] Fire error: {e}")

            # Refresh stale sessions
            now = time.time()
            for account in self.accounts:
                email = account["email"]
                last = self.last_login.get(email, 0)
                if now - last > SESSION_REFRESH and email in self.pages:
                    log.info(f"[DAEMON] Refreshing session for {email}")
                    await self._refresh_session(account)
                    await asyncio.sleep(2)

            await asyncio.sleep(1)  # Poll every 1s

    async def _send_discord(self, msg):
        try:
            if not WEBHOOK_FILE.exists():
                return
            wh = WEBHOOK_FILE.read_text().strip()
            if not wh:
                return
            import aiohttp
            async with aiohttp.ClientSession() as s:
                await s.post(wh, json={"content": msg})
        except:
            pass


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


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="JC Torpedo Daemon")
    parser.add_argument("--fire", "-f", help="Direct fire (no daemon, exit after)")
    parser.add_argument("--test", action="store_true", help="Use test account only")
    args = parser.parse_args()

    if args.test:
        accounts = [TEST_ACCOUNT]
    else:
        accounts = ACCOUNTS

    daemon = TorpedoDaemon(accounts)
    await daemon.start()

    if args.fire:
        # Direct fire mode (one-shot, exit after)
        await daemon.fire(args.fire)
        await daemon.browser.close()
    else:
        # Daemon mode (run forever, watch for triggers)
        log.info("[DAEMON] Entering daemon loop (watching /tmp/jc_torpedo_fire.txt)")
        try:
            await daemon.run_daemon()
        except KeyboardInterrupt:
            log.info("[DAEMON] Shutting down")
        finally:
            await daemon.browser.close()


if __name__ == "__main__":
    asyncio.run(main())
