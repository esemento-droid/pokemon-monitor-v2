#!/usr/bin/env python3
"""
JC Torpedo Daemon — FINAL VERSION with SELF-POLLING

Architecture:
  - 1 patchright browser, 4 contexts (separate sessions per account)
  - Each account pre-staged on /order (BLIK + Kurier Inpost + checkboxes)
  - SELF-POLLS target products every 2-3s (faster than scraper!)
  - On restock detected: API cart swap + click submit = ~2s
  - Heartbeat every 5 min (keep session alive)
  - Full re-stage every 30 min (fresh csrf)

Self-polling:
  - Tries ATC on target product every 2-3s (from account #1 page)
  - If ATC returns 200 → product available → FIRE ALL ACCOUNTS
  - If ATC returns 400 (OOS) → continue polling
  - No separate API endpoint needed — ATC itself is the stock check

Total time from restock to order: ~1.5s (ATC already done in poll + submit)

Trigger:
  - Self-poll (primary — fastest)
  - File: echo "PRODUCT_ID" > /tmp/jc_torpedo_fire.txt (backup from scraper)
  - CLI: --fire PID (manual)

Usage:
  DISPLAY=:99 ./venv/bin/python3 jc_torpedo_daemon.py --daemon --watch 9419
  DISPLAY=:99 ./venv/bin/python3 jc_torpedo_daemon.py --test --fire 7437
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

# Stage products (fallback list — use first available, cheap, high stock)
STAGE_PRODUCTS = [
    {"pid": 7437, "url": f"{SHOP_URL}/Pokemon-TCG-Angielski-Mega-Heroes-Mini-Tin-p7437"},      # Mini Tin 70 PLN, qty=17
    {"pid": 7589, "url": f"{SHOP_URL}/Pokemon-TCG-Angielski-Kanto-Friends-Mini-Tin-p7589"},    # Kanto Tin 80 PLN, qty=11
    {"pid": 9332, "url": f"{SHOP_URL}/PokeRadioStation-Angielski-Mystery-Pack-S4-p9332"},      # Mystery Pack 120 PLN, qty=20
    {"pid": 9334, "url": f"{SHOP_URL}/PokeRadioStation-Zestaw-Mystery-Packow-p9334"},          # Mystery Zestaw 228 PLN, qty=20
]

HEARTBEAT_INTERVAL = 300  # 5 min
RESTAGE_INTERVAL = 1800   # 30 min
POLL_INTERVAL = 5         # seconds between stock polls (safe: 12 req/min)


class TorpedoDaemon:
    def __init__(self, accounts, watch_pids=None):
        self.accounts = accounts
        self.watch_pids = watch_pids or []  # Product IDs to poll for restocks
        self.browser = None
        self._pw = None
        # Per-account state
        self.contexts = {}   # email -> browser context
        self.pages = {}      # email -> page (on /order, pre-staged)
        self.staged = {}     # email -> True if checkout is staged
        self.last_heartbeat = {}
        self.last_stage = {}
        self._fired_pids = set()  # Already fired (don't double-fire)

    # ==============================================================
    # STARTUP
    # ==============================================================

    async def start(self):
        from patchright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
            proxy=PROXY,
        )
        log.info("[DAEMON] Browser started (patchright stealth + proxy)")

        # Login + stage all accounts (with retry on failure)
        for acc in self.accounts:
            for attempt in range(3):
                try:
                    await self._full_stage(acc)
                    if self.staged.get(acc["email"]):
                        break
                except Exception as e:
                    log.error(f"[DAEMON] [{acc['email']}] Stage attempt {attempt+1}/3 failed: {e}")
                    if attempt < 2:
                        await asyncio.sleep(10)

            await asyncio.sleep(3)

        ok = sum(1 for v in self.staged.values() if v)
        log.info(f"[DAEMON] {ok}/{len(self.accounts)} accounts staged and ready 🚀")

        # If zero staged, try restarting browser with direct connection (no proxy)
        if ok == 0:
            log.warning("[DAEMON] 0 accounts staged — retrying WITHOUT proxy...")
            try:
                await self.browser.close()
            except:
                pass
            self.browser = await self._pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
            )
            for acc in self.accounts:
                try:
                    await self._full_stage(acc)
                except Exception as e:
                    log.error(f"[DAEMON] [{acc['email']}] Direct stage failed: {e}")
                await asyncio.sleep(3)
            ok = sum(1 for v in self.staged.values() if v)
            log.info(f"[DAEMON] After direct retry: {ok}/{len(self.accounts)} staged")

    # ==============================================================
    # LOGIN + STAGE (full checkout prep)
    # ==============================================================

    async def _full_stage(self, account):
        """Login, ATC stage product, go to /order, select BLIK+delivery+checkboxes."""
        email = account["email"]
        
        # Close old context if exists
        if email in self.contexts:
            try:
                await self.contexts[email].close()
            except:
                pass

        ctx = await self.browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=UA,
        )
        page = await ctx.new_page()
        self.contexts[email] = ctx
        self.pages[email] = page
        self.staged[email] = False

        # --- LOGIN ---
        await page.goto(f"{SHOP_URL}/login", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)
        await page.evaluate("""() => {
            document.getElementById('cc--main')?.remove();
            const btn = document.querySelector('.skyshop-alert-conditional-access button');
            if (btn) btn.click();
        }""")
        await page.wait_for_timeout(1000)
        await page.fill("input#email", email, timeout=5000)
        await page.fill("input[name='password']", account["password"], timeout=5000)
        await page.click("button[name='submit']", force=True)
        await page.wait_for_timeout(3000)

        content = await page.content()
        if "Moje konto" not in content and "Wyloguj" not in content:
            log.error(f"[{email}] Login FAILED")
            return

        log.info(f"[{email}] Logged in ✓")

        # --- CLEAR CART ---
        await page.goto(f"{SHOP_URL}/cart/", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)
        await page.evaluate("""() => {
            document.getElementById('cc--main')?.remove();
            document.querySelector('.fixed-elements')?.remove();
            document.querySelectorAll('[data-click="deleteCartItem"], .icon-close_24, [data-ng-click*="delete"]').forEach(b => b.click());
        }""")
        await page.wait_for_timeout(2000)

        # --- ATC STAGE PRODUCT (try from fallback list) ---
        atc_ok = False
        for stage in STAGE_PRODUCTS:
            await page.goto(stage["url"], wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.querySelector('.fixed-elements')?.remove();
            }""")
            try:
                atc_btn = page.locator("button:has-text('Do koszyka'), button[aria-label*='Dodaj do koszyka']").first
                await atc_btn.wait_for(state="visible", timeout=5000)
                await atc_btn.click(force=True)
                await page.wait_for_timeout(2000)
                try:
                    r = page.locator("text=Realizuj zamówienie")
                    if await r.is_visible(timeout=2000):
                        await r.click()
                except:
                    pass
                atc_ok = True
                log.info(f"[{email}] Stage product: {stage['pid']} ✓")
                break
            except:
                log.warning(f"[{email}] Stage product {stage['pid']} unavailable, trying next...")
                continue

        if not atc_ok:
            log.error(f"[{email}] ALL stage products unavailable!")
            return

        # --- GO TO CART → CHECKOUT ---
        await page.goto(f"{SHOP_URL}/cart/", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)
        await page.evaluate("""() => {
            document.getElementById('cc--main')?.remove();
            document.querySelector('.fixed-elements')?.remove();
        }""")
        checkout_btn = page.locator("button[data-ng-click='order()']:not([disabled])")
        await checkout_btn.wait_for(state="visible", timeout=20000)
        await checkout_btn.click(force=True)
        await page.wait_for_url("**/order**", timeout=15000)
        await page.wait_for_timeout(3000)

        # --- SELECT BLIK ---
        await page.evaluate("""() => {
            document.getElementById('cc--main')?.remove();
            document.querySelector('.fixed-elements')?.remove();
        }""")
        for _ in range(15):
            has = await page.evaluate("() => document.body.innerText.includes('BLIK')")
            if has:
                break
            await page.wait_for_timeout(1000)

        blik = page.locator("text=BLIK").first
        await blik.wait_for(state="visible", timeout=10000)
        await blik.click(force=True)
        await page.wait_for_timeout(3000)

        # --- SELECT DELIVERY ---
        for _ in range(15):
            has = await page.evaluate("() => document.body.innerText.includes('Kurier Inpost')")
            if has:
                break
            await page.wait_for_timeout(1000)

        try:
            d = page.locator("text=Kurier Inpost - Gabaryt C >> visible=true")
            if await d.count() > 0:
                await d.first.click(force=True)
            else:
                d = page.locator("input#param-delivery-6512b")
                if await d.count() > 0:
                    await d.evaluate("el => el.closest('tr,div')?.click() || el.click()")
                else:
                    await page.evaluate("""() => {
                        const rows = document.querySelectorAll('tr, div, label');
                        for (const r of rows) {
                            if (r.textContent.includes('Kurier') && r.textContent.includes('Inpost')) {
                                const radio = r.querySelector('input[type="radio"]');
                                if (radio) radio.click(); else r.click();
                                return;
                            }
                        }
                    }""")
        except:
            pass

        await page.wait_for_timeout(1500)

        # --- CHECKBOXES ---
        await page.evaluate("""() => {
            window.scrollTo(0, document.body.scrollHeight);
            document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                if (cb.getAttribute('data-valid')?.includes('required') && !cb.checked) cb.click();
            });
        }""")
        await page.wait_for_timeout(500)

        # --- VERIFY ---
        state = await page.evaluate("""() => {
            const csrf = document.querySelector('input[name=csrf_token]')?.value || '';
            const btn = document.querySelector('button[name=finish]');
            const radios = [...document.querySelectorAll('input[type=radio]:checked')].map(r => r.name + '=' + r.value);
            return {csrf: csrf.length > 10, btn_ok: btn && !btn.disabled, radios};
        }""")

        if state.get("csrf") and state.get("btn_ok"):
            self.staged[email] = True
            self.last_stage[email] = time.time()
            self.last_heartbeat[email] = time.time()
            log.info(f"[{email}] ✅ STAGED (radios={state['radios']})")
        else:
            log.error(f"[{email}] ❌ Stage incomplete: {state}")

    # ==============================================================
    # FIRE TORPEDO (~2s)
    # ==============================================================

    async def fire(self, product_id, product_url=""):
        """Fire on all staged accounts in PARALLEL."""
        t0 = time.time()
        active = [email for email, ok in self.staged.items() if ok]

        if not active:
            log.error("[FIRE] No staged accounts!")
            return 0

        # Skip accounts that already bought this product
        completed = _load_completed()
        pid_str = str(product_id)
        active = [e for e in active if e not in completed.get(pid_str, [])]

        if not active:
            log.info(f"[FIRE] All accounts already completed product {product_id} — skip")
            return 0

        log.info(f"=== 🚀 TORPEDO FIRE product={product_id} ({len(active)} accounts) ===")
        await self._discord(f"🚀 **TORPEDO FIRE** product {product_id} — {len(active)} accounts")

        tasks = [self._fire_one(email, product_id, t0) for email in active]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        total = time.time() - t0
        ok = sum(1 for r in results if r is True)
        failed = [email for email, r in zip(active, results) if r is not True]

        log.info(f"=== TORPEDO DONE: {ok}/{len(active)} in {total:.2f}s ===")
        await self._discord(f"{'✅' if ok else '❌'} **TORPEDO** {product_id} | {ok}/{len(active)} | {total:.1f}s")

        # Mark staged=False for accounts that fired (need re-stage)
        for email in active:
            self.staged[email] = False

        return ok

    async def _fire_one(self, email, product_id, t0):
        """
        HOT PATH — target <2s:
        1. API: clear cart + ATC target product (0.5-1s)
           (skip if product already in cart from poll)
        2. Click "Zamawiam i płacę" (1s)
        """
        page = self.pages.get(email)
        if not page:
            return False

        try:
            # === API CART SWAP (from browser JS — same session) ===
            swap_result = await page.evaluate(f"""async () => {{
                const cartId = document.cookie.match(/sky2_cart_id=([^;]+)/)?.[1];
                if (!cartId) return {{error: 'no_cart_id'}};

                // Check if target product already in cart (from poll ATC)
                const cartResp = await fetch('/proxy_public_api?endpoint=/sky2/api-public/carts/bulk/' + cartId, {{
                    headers: {{'Accept':'application/json','currency':'PLN','lang':'pl'}}
                }});
                const cartData = await cartResp.json();
                const items = cartData.cart?.items || [];
                const hasTarget = items.some(i => i.product?.id === {product_id});
                
                if (hasTarget && items.length === 1) {{
                    // Already have ONLY target product (from poll) — skip swap
                    return {{ok: true, skipped: true, price: items[0].priceSummary?.final?.grossDisplay}};
                }}

                // Clear all items
                await Promise.all(items.map(item =>
                    fetch('/proxy_public_api?endpoint=/sky2/api-public/carts/' + cartId + '/items/' + item.id, {{
                        method: 'DELETE',
                        headers: {{'Accept':'application/json','currency':'PLN','lang':'pl'}}
                    }})
                ));

                // ATC target product
                const atcResp = await fetch('/proxy_public_api?endpoint=/sky2/api-public/carts/' + cartId + '/items', {{
                    method: 'POST',
                    headers: {{'Content-Type':'application/json','Accept':'application/json','currency':'PLN','lang':'pl'}},
                    body: JSON.stringify({{productId: {product_id}, quantity: 1, parameters: []}})
                }});
                const atcData = await atcResp.json();
                
                if (atcData.addedCartItem) {{
                    return {{ok: true, skipped: false, price: atcData.addedCartItem.priceSummary?.final?.grossDisplay}};
                }} else {{
                    return {{ok: false, error: atcData.message || atcData.errorCode || 'unknown'}};
                }}
            }}""")

            if not swap_result.get("ok"):
                log.error(f"[{email}] ATC failed: {swap_result.get('error')}")
                return False

            skipped = swap_result.get("skipped", False)
            log.info(f"[{email}] ATC {'(from poll)' if skipped else 'OK'} ({swap_result.get('price')}) ({time.time()-t0:.2f}s)")

            # === CLICK SUBMIT ===
            await page.click("button[name='finish']", force=True)
            await page.wait_for_timeout(5000)

            final_url = page.url
            total = time.time() - t0
            success = any(kw in final_url.lower() for kw in ["autopay", "blik", "tpay", "przelewy24", "potwierdzenie", "thank", "pay"])

            if success:
                log.info(f"[{email}] ✅ ORDER in {total:.2f}s! → {final_url[:60]}")
                _mark_completed(product_id, email)
                return True
            else:
                log.error(f"[{email}] ❌ Submit failed ({total:.2f}s) URL: {final_url[:60]}")
                return False

        except Exception as e:
            log.error(f"[{email}] Exception: {e}")
            return False

    # ==============================================================
    # MAINTENANCE (heartbeat + re-stage)
    # ==============================================================

    async def _heartbeat(self, email):
        """Keep session alive (fetch cart API). Detect stale pages."""
        page = self.pages.get(email)
        if not page:
            return
        try:
            await page.evaluate("""() => fetch('/proxy_public_api?endpoint=/sky2/api-public/carts/bulk/latest', {headers: {'Accept':'application/json','currency':'PLN','lang':'pl'}})""")
            self.last_heartbeat[email] = time.time()
        except Exception as e:
            err_str = str(e)
            if any(x in err_str for x in ["Target page", "browser has been closed",
                                            "context or browser", "closed"]):
                log.warning(f"[{email}] Heartbeat: page stale ({err_str[:50]}) — marking unstaged")
                self.staged[email] = False
            else:
                log.warning(f"[{email}] Heartbeat failed: {err_str[:60]}")

    async def maintenance(self):
        """Run heartbeats and re-stages."""
        now = time.time()
        for acc in self.accounts:
            email = acc["email"]
            if email not in self.pages:
                continue

            # Heartbeat every 5 min
            if now - self.last_heartbeat.get(email, 0) > HEARTBEAT_INTERVAL:
                await self._heartbeat(email)

            # Re-stage every 30 min OR if not staged
            if not self.staged.get(email) or (now - self.last_stage.get(email, 0) > RESTAGE_INTERVAL):
                log.info(f"[DAEMON] Re-staging {email}...")
                for attempt in range(3):
                    try:
                        await self._full_stage(acc)
                        if self.staged.get(email):
                            break
                    except Exception as e:
                        log.error(f"[DAEMON] Re-stage {email} attempt {attempt+1}/3 failed: {e}")
                        if attempt < 2:
                            await asyncio.sleep(5)
                await asyncio.sleep(3)

        # If ALL accounts unstaged — try full browser restart every 10 min
        ok = sum(1 for v in self.staged.values() if v)
        if ok == 0 and not hasattr(self, '_last_full_restart'):
            self._last_full_restart = 0
        if ok == 0 and (now - getattr(self, '_last_full_restart', 0)) > 600:
            log.warning("[DAEMON] 0 staged accounts — full browser restart")
            self._last_full_restart = now
            await self._nuclear_restart()

    async def _nuclear_restart(self):
        """Full browser restart with proxy fallback. Handles stale _pw gracefully."""
        try:
            # Close old browser
            if self.browser:
                try:
                    await self.browser.close()
                except Exception:
                    pass
            self.browser = None

            # Close and recreate playwright instance (prevents stale state)
            if self._pw:
                try:
                    await self._pw.stop()
                except Exception:
                    pass
            self._pw = None

            from patchright.async_api import async_playwright
            self._pw = await async_playwright().start()

            # Try with proxy first
            try:
                self.browser = await self._pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
                    proxy=PROXY,
                )
                log.info("[DAEMON] Browser restarted (with proxy)")
            except Exception as e:
                log.warning(f"[DAEMON] Proxy launch failed ({e}) — trying direct...")
                self.browser = await self._pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
                )
                log.info("[DAEMON] Browser restarted (direct, no proxy)")

            # Clear stale page/context references
            self.contexts.clear()
            self.pages.clear()

            # Re-stage all accounts with retry
            log.info("[DAEMON] Re-staging all accounts after restart...")
            for acc in self.accounts:
                for attempt in range(3):
                    try:
                        await self._full_stage(acc)
                        if self.staged.get(acc["email"]):
                            break
                    except Exception as e:
                        log.error(f"[DAEMON] Re-stage after restart {acc['email']} attempt {attempt+1}/3: {e}")
                        if attempt < 2:
                            await asyncio.sleep(5)
                await asyncio.sleep(3)

            ok = sum(1 for v in self.staged.values() if v)
            log.info(f"[DAEMON] After nuclear restart: {ok}/{len(self.accounts)} staged")
            if ok > 0:
                await self._discord(f"♻️ **TORPEDO RESTART** — {ok}/{len(self.accounts)} staged")

        except Exception as e:
            log.error(f"[DAEMON] Nuclear restart FAILED: {e}")
            await self._discord(f"❌ **TORPEDO** nuclear restart failed: {e}")

    # ==============================================================
    # STOCK POLLING (self-monitoring, faster than scraper)
    # ==============================================================

    async def _poll_stock(self):
        """
        Poll target products via ATC attempt.
        If ATC returns 200 → product available → FIRE!
        If ATC returns 400 (ERROR_PRODUCT_OUT_OF_STOCK) → still OOS, continue.
        Uses first staged account's page for fetch().
        """
        if not self.watch_pids:
            return

        # Use first staged account for polling
        poll_email = next((e for e, ok in self.staged.items() if ok), None)
        if not poll_email:
            # No staged accounts — skip polling silently (maintenance will fix this)
            return

        page = self.pages.get(poll_email)
        if not page:
            return

        for pid in self.watch_pids:
            if pid in self._fired_pids:
                continue

            try:
                result = await page.evaluate(f"""async () => {{
                    const cartId = document.cookie.match(/sky2_cart_id=([^;]+)/)?.[1];
                    if (!cartId) return {{error: 'no_cart_id'}};
                    
                    // Clear cart first (remove stage product)
                    const cartResp = await fetch('/proxy_public_api?endpoint=/sky2/api-public/carts/bulk/' + cartId, {{
                        headers: {{'Accept':'application/json','currency':'PLN','lang':'pl'}}
                    }});
                    const cartData = await cartResp.json();
                    const items = cartData.cart?.items || [];
                    await Promise.all(items.map(item =>
                        fetch('/proxy_public_api?endpoint=/sky2/api-public/carts/' + cartId + '/items/' + item.id, {{
                            method: 'DELETE', headers: {{'Accept':'application/json','currency':'PLN','lang':'pl'}}
                        }})
                    ));
                    
                    // Try ATC target product
                    const resp = await fetch('/proxy_public_api?endpoint=/sky2/api-public/carts/' + cartId + '/items', {{
                        method: 'POST',
                        headers: {{'Content-Type':'application/json','Accept':'application/json','currency':'PLN','lang':'pl'}},
                        body: JSON.stringify({{productId: {pid}, quantity: 1, parameters: []}})
                    }});
                    const data = await resp.json();
                    
                    if (data.addedCartItem) {{
                        return {{available: true, price: data.addedCartItem.priceSummary?.final?.grossDisplay}};
                    }} else {{
                        // OOS — re-add stage product to keep checkout valid
                        await fetch('/proxy_public_api?endpoint=/sky2/api-public/carts/' + cartId + '/items', {{
                            method: 'POST',
                            headers: {{'Content-Type':'application/json','Accept':'application/json','currency':'PLN','lang':'pl'}},
                            body: JSON.stringify({{productId: {STAGE_PRODUCTS[0]['pid']}, quantity: 1, parameters: []}})
                        }});
                        return {{available: false, error: data.errorCode || data.message || 'unknown'}};
                    }}
                }}""")

                if result.get("available"):
                    # RESTOCK DETECTED! Product is available!
                    log.info(f"[POLL] 🔥 RESTOCK DETECTED: product {pid} ({result.get('price')})!")
                    self._fired_pids.add(pid)

                    # Product is ALREADY in poll account's cart from the ATC check.
                    # For this account: just click submit (0s ATC — already done!)
                    # For other accounts: need cart swap (1s)

                    # Fire all accounts
                    await self.fire(str(pid))
                    return  # Don't poll other products, focus on fire

            except Exception as e:
                log.warning(f"[POLL] Error polling {pid}: {e}")

    # ==============================================================
    # DAEMON LOOP
    # ==============================================================

    async def run(self):
        """Main daemon loop: self-poll + watch trigger file + maintenance."""
        log.info(f"[DAEMON] Running. Watching products: {self.watch_pids}")
        log.info(f"[DAEMON] Poll interval: {POLL_INTERVAL}s | Also watching /tmp/jc_torpedo_fire.txt")
        last_maintenance = 0
        last_poll = 0

        while True:
            now = time.time()

            # Stock polling (primary trigger — fastest)
            if self.watch_pids and (now - last_poll) >= POLL_INTERVAL:
                await self._poll_stock()
                # Add random jitter (3-7s total interval) to avoid bot detection
                import random
                last_poll = time.time() + random.uniform(-1, 2)

            # Check trigger file (backup trigger from scraper)
            if FIRE_FILE.exists():
                try:
                    content = FIRE_FILE.read_text().strip()
                    FIRE_FILE.unlink()
                    parts = content.split(" ", 1)
                    product_id = parts[0]
                    if product_id and product_id not in self._fired_pids:
                        log.info(f"[DAEMON] Trigger file: product {product_id}")
                        await self.fire(product_id)
                        self._fired_pids.add(product_id)
                except Exception as e:
                    log.error(f"[DAEMON] Fire error: {e}")

            # Maintenance every 60s
            if now - last_maintenance > 60:
                await self.maintenance()
                last_maintenance = now

            await asyncio.sleep(0.5)

    # ==============================================================
    # HELPERS
    # ==============================================================

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
    data = _load_completed()
    pid = str(product_id)
    if pid not in data:
        data[pid] = []
    if email not in data[pid]:
        data[pid].append(email)
    COMPLETED_FILE.write_text(json.dumps(data, indent=2))


def _load_completed():
    if COMPLETED_FILE.exists():
        try:
            return json.loads(COMPLETED_FILE.read_text())
        except:
            pass
    return {}


# ==============================================================
# CLI
# ==============================================================

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="JC Torpedo Daemon — ~2s buy")
    parser.add_argument("--fire", "-f", help="Product ID to buy NOW")
    parser.add_argument("--url", "-u", default="", help="Product URL")
    parser.add_argument("--test", action="store_true", help="Use test account (Marian)")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon (poll + watch trigger)")
    parser.add_argument("--watch", "-w", nargs="+", help="Product IDs to poll for restocks (daemon mode)")
    args = parser.parse_args()

    accounts = [TEST_ACCOUNT] if args.test else ACCOUNTS
    watch_pids = [int(p) for p in args.watch] if args.watch else []
    daemon = TorpedoDaemon(accounts, watch_pids=watch_pids)

    await daemon.start()

    if args.fire:
        await daemon.fire(args.fire)
        await daemon.browser.close()
    elif args.daemon:
        try:
            await daemon.run()
        except KeyboardInterrupt:
            log.info("[DAEMON] Shutting down")
        finally:
            await daemon.browser.close()
    else:
        print("Usage:")
        print("  --daemon --watch 9419          Poll product 9419, fire on restock")
        print("  --daemon --watch 9419 9420     Poll multiple products")
        print("  --fire 9419                    Buy product NOW (one-shot)")
        print("  --fire 7437 --test             Buy on test account")
        print("")
        print("Daemon self-polls every 2.5s. Also watches /tmp/jc_torpedo_fire.txt")
        await daemon.browser.close()


if __name__ == "__main__":
    asyncio.run(main())
