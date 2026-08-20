#!/usr/bin/env python3
"""
JC Torpedo Daemon — persistent browser, same checkout flow as working bot.

Copied EXACTLY from japancollectibles_autobuy.py (which works) but:
- Browser always running (no cold start)
- Accounts pre-logged (no login time)
- Reduced waits (minimum needed)
- 4 accounts fire in PARALLEL (not sequential)
- Trigger via file: echo "PRODUCT_ID URL" > /tmp/jc_torpedo_fire.txt

Target: ~10s total (vs 70s per account old bot)
"""
import asyncio
import json
import logging
import os
import sys
import time
import re
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
SESSION_REFRESH = 2700  # 45 min


class TorpedoDaemon:
    def __init__(self, accounts):
        self.accounts = accounts
        self.browser = None
        self.contexts = {}  # email -> context (separate sessions!)
        self.pages = {}  # email -> page
        self.last_login = {}
        self._pw = None

    async def start(self):
        from patchright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
            proxy=PROXY,
        )
        log.info("[DAEMON] Browser started")

        for acc in self.accounts:
            await self._login(acc)
            await asyncio.sleep(2)

        log.info(f"[DAEMON] {len(self.pages)} accounts ready")

    async def _login(self, account):
        """Login account — SAME flow as working japancollectibles_autobuy.py"""
        email = account["email"]
        # Each account gets own context (separate cookies/session)
        ctx = await self.browser.new_context(viewport={"width": 1280, "height": 900}, user_agent=UA)
        page = await ctx.new_page()

        try:
            # Dismiss age gate + go to login
            await page.goto(SHOP_URL, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                const btn = document.querySelector('.skyshop-alert-conditional-access button');
                if (btn) btn.click();
            }""")
            await page.wait_for_timeout(1000)

            await page.goto(f"{SHOP_URL}/login", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.querySelector('.fixed-elements')?.remove();
            }""")

            await page.wait_for_selector("input#email", timeout=10000)
            await page.fill("input#email", email)
            await page.fill("input[name='password']", account["password"])
            await page.click("button[name='submit']", force=True)
            await page.wait_for_timeout(3000)

            content = await page.content()
            if "Moje konto" in content or "Wyloguj" in content:
                self.contexts[email] = ctx
                self.pages[email] = page
                self.last_login[email] = time.time()
                log.info(f"[DAEMON] [{email}] Logged in ✓")
            else:
                log.error(f"[DAEMON] [{email}] Login FAILED")
                await ctx.close()
        except Exception as e:
            log.error(f"[DAEMON] [{email}] Login error: {e}")
            try:
                await ctx.close()
            except:
                pass

    async def fire(self, product_id, product_url=""):
        """Fire on all accounts in PARALLEL — same checkout flow as working bot."""
        t0 = time.time()
        if not product_url:
            product_url = f"{SHOP_URL}/-p{product_id}"

        log.info(f"=== 🚀 TORPEDO FIRE product={product_id} ({len(self.pages)} accounts) ===")
        await self._discord(f"🚀 **TORPEDO** product {product_id} — {len(self.pages)} accounts")

        tasks = [self._buy(email, product_id, product_url, t0) for email in self.pages]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        total = time.time() - t0
        ok = sum(1 for r in results if r is True)
        log.info(f"=== TORPEDO DONE: {ok}/{len(tasks)} in {total:.1f}s ===")
        await self._discord(f"{'✅' if ok else '❌'} **TORPEDO** {product_id} | {ok}/{len(tasks)} | {total:.1f}s")
        return ok

    async def _buy(self, email, product_id, product_url, t0):
        """
        Buy flow — COPIED from japancollectibles_autobuy.py (which works).
        Only difference: no login (already logged in), reduced waits.
        """
        page = self.pages.get(email)
        if not page:
            return False

        try:
            # === 1. CLEAR CART ===
            await page.goto(f"{SHOP_URL}/cart/", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.querySelector('.fixed-elements')?.remove();
            }""")
            await page.evaluate("""() => {
                const delBtns = document.querySelectorAll('[data-click="deleteCartItem"], button[aria-label*="Usuń"], .icon-close_24, [data-ng-click*="delete"]');
                delBtns.forEach(btn => btn.click());
            }""")
            await page.wait_for_timeout(1500)

            # === 2. ADD TO CART (go to product page, click "Do koszyka") ===
            await page.goto(product_url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.querySelector('.fixed-elements')?.remove();
            }""")

            atc_btn = page.locator("button:has-text('Do koszyka'), button[aria-label*='Dodaj do koszyka']").first
            await atc_btn.wait_for(state="visible", timeout=8000)
            await atc_btn.click(force=True)
            log.info(f"[{email}] ATC click ({time.time()-t0:.1f}s)")
            await page.wait_for_timeout(2000)

            # Dismiss popup
            try:
                realize = page.locator("text=Realizuj zamówienie")
                if await realize.is_visible(timeout=3000):
                    await realize.click()
                    await page.wait_for_timeout(1000)
            except:
                pass

            # === 3. CART → CHECKOUT ===
            await page.goto(f"{SHOP_URL}/cart/", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(3000)
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.querySelector('.fixed-elements')?.remove();
            }""")

            # Wait for checkout button enabled
            checkout_btn = page.locator("button[data-ng-click='order()']:not([disabled])")
            await checkout_btn.wait_for(state="visible", timeout=15000)
            await checkout_btn.click(force=True)

            # Wait for /order page
            await page.wait_for_url("**/order**", timeout=15000)
            await page.wait_for_timeout(3000)
            log.info(f"[{email}] Checkout page ({time.time()-t0:.1f}s)")

            # === 4. PAYMENT: BLIK ===
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.querySelector('.fixed-elements')?.remove();
            }""")

            for _ in range(10):
                has = await page.evaluate("() => document.body.innerText.includes('BLIK')")
                if has:
                    break
                await page.wait_for_timeout(1500)

            payment_el = page.locator("text=BLIK").first
            await payment_el.wait_for(state="visible", timeout=10000)
            await payment_el.click(force=True)
            log.info(f"[{email}] Payment: BLIK ({time.time()-t0:.1f}s)")
            await page.wait_for_timeout(3000)

            # === 5. DELIVERY: Kurier Inpost ===
            for _ in range(10):
                has = await page.evaluate("() => document.body.innerText.includes('Kurier Inpost')")
                if has:
                    break
                await page.wait_for_timeout(1500)

            delivery_clicked = False
            try:
                del_el = page.locator("text=Kurier Inpost - Gabaryt C >> visible=true")
                if await del_el.count() > 0:
                    await del_el.first.click(force=True)
                    delivery_clicked = True
                else:
                    del_el = page.locator("input#param-delivery-6512b")
                    if await del_el.count() > 0:
                        await del_el.evaluate("el => el.closest('tr, div')?.click() || el.click()")
                        delivery_clicked = True
                    else:
                        del_el = page.locator("td:has-text('Kurier Inpost'), div:has-text('Kurier Inpost')").first
                        await del_el.click(force=True, timeout=5000)
                        delivery_clicked = True
            except:
                pass

            if not delivery_clicked:
                await page.evaluate("""() => {
                    const rows = document.querySelectorAll('tr, div, label');
                    for (const r of rows) {
                        if (r.textContent.includes('Kurier') && r.textContent.includes('Inpost')) {
                            const radio = r.querySelector('input[type="radio"]');
                            if (radio) { radio.click(); return; }
                            r.click(); return;
                        }
                    }
                }""")

            log.info(f"[{email}] Delivery selected ({time.time()-t0:.1f}s)")
            await page.wait_for_timeout(1500)

            # === 6. CHECKBOXES ===
            await page.evaluate("""() => {
                window.scrollTo(0, document.body.scrollHeight);
            }""")
            await page.wait_for_timeout(500)
            await page.evaluate("""() => {
                document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                    const req = cb.getAttribute('data-valid')?.includes('required');
                    if (req && !cb.checked) cb.click();
                });
            }""")
            await page.wait_for_timeout(500)

            # === 7. SUBMIT ===
            log.info(f"[{email}] Submitting ({time.time()-t0:.1f}s)")
            order_btn = page.locator("button[name='finish']").first
            await order_btn.wait_for(state="visible", timeout=5000)
            await order_btn.click(force=True)

            await page.wait_for_timeout(5000)
            final_url = page.url
            total = time.time() - t0

            success = any(kw in final_url.lower() for kw in ["potwierdzenie", "thank", "tpay", "blik", "przelewy24"])
            if not success:
                content = await page.content()
                success = any(kw in content.lower() for kw in ["zamówienie zostało złożone", "dziękujemy"])

            if success:
                log.info(f"[{email}] ✅ ORDER in {total:.1f}s! → {final_url[:60]}")
                _mark_completed(product_id, email)
                return True
            else:
                log.error(f"[{email}] ❌ Failed ({total:.1f}s) URL: {final_url[:60]}")
                await page.screenshot(path=f"/tmp/jc_torpedo_{email.split('@')[0]}.png")
                return False

        except Exception as e:
            log.error(f"[{email}] Exception: {e}")
            return False

    async def daemon_loop(self):
        """Watch trigger file + refresh sessions."""
        while True:
            if FIRE_FILE.exists():
                try:
                    content = FIRE_FILE.read_text().strip()
                    FIRE_FILE.unlink()
                    parts = content.split(" ", 1)
                    product_id = parts[0]
                    product_url = parts[1] if len(parts) > 1 else ""
                    if product_id:
                        await self.fire(product_id, product_url)
                except Exception as e:
                    log.error(f"[DAEMON] Fire error: {e}")

            # Session refresh
            now = time.time()
            for acc in self.accounts:
                email = acc["email"]
                if email in self.pages and (now - self.last_login.get(email, 0)) > SESSION_REFRESH:
                    log.info(f"[DAEMON] Refreshing {email}")
                    try:
                        await self.contexts[email].close()
                    except:
                        pass
                    del self.pages[email]
                    del self.contexts[email]
                    await self._login(acc)

            await asyncio.sleep(0.5)

    async def _discord(self, msg):
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--fire", "-f", help="Product ID (one-shot)")
    parser.add_argument("--url", "-u", default="", help="Product URL")
    parser.add_argument("--test", action="store_true", help="Test account only")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    args = parser.parse_args()

    accounts = [TEST_ACCOUNT] if args.test else ACCOUNTS
    daemon = TorpedoDaemon(accounts)
    await daemon.start()

    if args.fire:
        await daemon.fire(args.fire, args.url)
        await daemon.browser.close()
    elif args.daemon:
        log.info("[DAEMON] Running (watch /tmp/jc_torpedo_fire.txt)")
        try:
            await daemon.daemon_loop()
        except KeyboardInterrupt:
            pass
        finally:
            await daemon.browser.close()
    else:
        print("--fire PID or --daemon")


if __name__ == "__main__":
    asyncio.run(main())
