#!/usr/bin/env python3
"""
JapanCollectibles TORPEDO — instant HTTP buy (no browser, <2s per account)

Sky-Shop platform endpoints (discovered):
  - Age gate:  GET / + follow cookie
  - Login:     POST /login {email, password, submit}
  - ATC:       GET /cart/add/{product_id}
  - Order:     GET /order → POST /order {payment, delivery, checkboxes}

Architecture:
  - Pre-warmed sessions: login + cookies cached at startup (session_warmer)
  - On trigger: ATC + checkout = 2-3 HTTP requests = <1 second
  - Parallel: all 4 accounts fire simultaneously (asyncio.gather)
  - No browser, no JS render, no overlays, no clicking

Called by japancollectibles_trigger.py (replaces browser bot for speed).
"""
import asyncio
import json
import logging
import os
import sys
import time
import re
from pathlib import Path
from http.cookies import SimpleCookie

import aiohttp

BASE_DIR = Path("/opt/pokemon-monitor-v2")
SESSION_DIR = BASE_DIR / "data" / "jc_sessions"
COMPLETED_FILE = BASE_DIR / "japancollectibles_completed.json"
LOG_FILE = BASE_DIR / "japancollectibles_torpedo.log"
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

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
PROXY = "http://127.0.0.1:8888"


# ============================================================
# SESSION MANAGEMENT (pre-warmed cookies)
# ============================================================

def _session_path(email):
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    safe = email.replace("@", "_at_").replace(".", "_")
    return SESSION_DIR / f"{safe}.json"


def _save_session(email, cookies_dict):
    path = _session_path(email)
    data = {"email": email, "cookies": cookies_dict, "ts": time.time()}
    path.write_text(json.dumps(data))


def _load_session(email):
    path = _session_path(email)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        # Sessions older than 50 min are stale (Sky-Shop session ~60min)
        if time.time() - data.get("ts", 0) > 3000:
            return None
        return data.get("cookies", {})
    except:
        return None


async def _create_session(account) -> dict:
    """Login and return session cookies dict. Pure HTTP."""
    email = account["email"]
    password = account["password"]
    cookies = {}

    connector = aiohttp.TCPConnector(ssl=False)
    jar = aiohttp.CookieJar(unsafe=True)

    async with aiohttp.ClientSession(
        connector=connector,
        cookie_jar=jar,
        headers={"User-Agent": UA},
    ) as session:
        # Step 1: Hit homepage to get initial session cookie + age gate
        try:
            async with session.get(SHOP_URL, proxy=PROXY, timeout=aiohttp.ClientTimeout(total=15), allow_redirects=True) as resp:
                await resp.text()
        except Exception as e:
            log.warning(f"[{email}] Homepage fetch failed: {e}")

        # Step 2: Confirm age gate (POST or GET with cookie)
        # Sky-Shop age gate sets cookie on confirmation click
        try:
            # Try POST to conditional-access endpoint
            async with session.post(
                f"{SHOP_URL}/conditional-access/confirm",
                proxy=PROXY,
                timeout=aiohttp.ClientTimeout(total=10),
                allow_redirects=True,
            ) as resp:
                await resp.text()
        except:
            # Fallback: GET with header
            try:
                async with session.get(
                    f"{SHOP_URL}/conditional-access/confirm",
                    proxy=PROXY,
                    timeout=aiohttp.ClientTimeout(total=10),
                    allow_redirects=True,
                ) as resp:
                    await resp.text()
            except:
                pass

        # Step 3: Login
        login_data = {
            "email": email,
            "password": password,
            "submit": "1",
        }
        try:
            async with session.post(
                f"{SHOP_URL}/login",
                data=login_data,
                proxy=PROXY,
                timeout=aiohttp.ClientTimeout(total=15),
                allow_redirects=True,
            ) as resp:
                html = await resp.text()
                if "Moje konto" in html or "Wyloguj" in html or resp.url.path in ("/", "/account"):
                    log.info(f"[{email}] Login OK")
                else:
                    # Try JSON login (some Sky-Shop versions)
                    log.warning(f"[{email}] Login uncertain, URL: {resp.url}")
        except Exception as e:
            log.error(f"[{email}] Login failed: {e}")
            return {}

        # Extract cookies
        for cookie in jar:
            cookies[cookie.key] = cookie.value

    if cookies:
        _save_session(email, cookies)
        log.info(f"[{email}] Session saved ({len(cookies)} cookies)")
    return cookies


async def warmup_all():
    """Pre-warm sessions for all accounts. Call from cron or session_warmer."""
    log.info("=== Warming up all JC sessions ===")
    tasks = [_create_session(acc) for acc in ACCOUNTS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    ok = sum(1 for r in results if r and not isinstance(r, Exception))
    log.info(f"=== Warmup done: {ok}/{len(ACCOUNTS)} sessions ready ===")
    return ok


# ============================================================
# TORPEDO (instant buy)
# ============================================================

async def torpedo_buy(account, product_id, product_url=""):
    """
    Instant buy: ATC + Checkout in pure HTTP. <2 seconds total.
    Returns True if order placed.
    """
    email = account["email"]
    t0 = time.time()

    # Load pre-warmed session
    cookies = _load_session(email)
    if not cookies:
        log.warning(f"[{email}] No warm session, creating fresh...")
        cookies = await _create_session(account)
        if not cookies:
            log.error(f"[{email}] Cannot create session, ABORT")
            return False

    connector = aiohttp.TCPConnector(ssl=False)
    jar = aiohttp.CookieJar(unsafe=True)

    async with aiohttp.ClientSession(
        connector=connector,
        cookie_jar=jar,
        headers={
            "User-Agent": UA,
            "Referer": SHOP_URL,
            "X-Requested-With": "XMLHttpRequest",
        },
    ) as session:
        # Load cookies into jar
        for name, value in cookies.items():
            jar.update_cookies({name: value}, response_url=aiohttp.client.URL(SHOP_URL))

        # === STEP 1: ADD TO CART (GET /cart/add/{id}) ===
        atc_url = f"{SHOP_URL}/cart/add/{product_id}"
        try:
            async with session.get(
                atc_url,
                proxy=PROXY,
                timeout=aiohttp.ClientTimeout(total=10),
                allow_redirects=True,
            ) as resp:
                atc_html = await resp.text()
                atc_time = time.time() - t0
                if resp.status == 200:
                    log.info(f"[{email}] ATC OK in {atc_time:.2f}s (product {product_id})")
                else:
                    log.error(f"[{email}] ATC failed HTTP {resp.status}")
                    return False
        except Exception as e:
            log.error(f"[{email}] ATC error: {e}")
            return False

        # Check if product was actually added (not sold out / requires login)
        if "pusty" in atc_html.lower() and "koszyk jest pusty" in atc_html.lower():
            log.error(f"[{email}] Cart empty after ATC — product sold out or session expired")
            # Invalidate session
            path = _session_path(email)
            if path.exists():
                path.unlink()
            return False

        # === STEP 2: GO TO ORDER PAGE ===
        try:
            async with session.get(
                f"{SHOP_URL}/order",
                proxy=PROXY,
                timeout=aiohttp.ClientTimeout(total=10),
                allow_redirects=True,
            ) as resp:
                order_html = await resp.text()
                if resp.status != 200:
                    log.error(f"[{email}] Order page HTTP {resp.status}")
                    return False
        except Exception as e:
            log.error(f"[{email}] Order page error: {e}")
            return False

        # === STEP 3: SUBMIT ORDER ===
        # Sky-Shop order form requires:
        # - payment method (ID)
        # - delivery method (ID)
        # - consent checkboxes
        # Extract form tokens/IDs from order page
        
        # Find payment radio (BLIK)
        payment_id = ""
        payment_match = re.search(r'id="param-payment-([^"]+)"[^>]*>.*?BLIK', order_html, re.DOTALL)
        if payment_match:
            payment_id = payment_match.group(1)
        else:
            # Fallback: find any payment with "blik" or "przelew"
            payment_match = re.search(r'id="param-payment-([^"]+)"[^>]*>.*?(?:blik|przelew|transfer)', order_html, re.DOTALL | re.IGNORECASE)
            if payment_match:
                payment_id = payment_match.group(1)
            else:
                # Last resort: first payment option
                payment_match = re.search(r'id="param-payment-([^"]+)"', order_html)
                if payment_match:
                    payment_id = payment_match.group(1)

        # Find delivery radio (Kurier Inpost Gabaryt C)
        delivery_id = ""
        delivery_match = re.search(r'id="param-delivery-([^"]+)"[^>]*>.*?(?:Kurier.*?Inpost|Gabaryt C)', order_html, re.DOTALL | re.IGNORECASE)
        if delivery_match:
            delivery_id = delivery_match.group(1)
        else:
            # Fallback: first delivery option
            delivery_match = re.search(r'id="param-delivery-([^"]+)"', order_html)
            if delivery_match:
                delivery_id = delivery_match.group(1)

        if not payment_id or not delivery_id:
            log.error(f"[{email}] Cannot find payment ({payment_id}) or delivery ({delivery_id}) IDs")
            log.error(f"[{email}] Order page snippet: {order_html[:2000]}")
            return False

        log.info(f"[{email}] Payment: {payment_id}, Delivery: {delivery_id}")

        # Find required checkboxes
        checkbox_names = re.findall(r'name="(agreement\[\d+\]|rules|consent[^"]*)"[^>]*data-valid[^>]*required', order_html)
        if not checkbox_names:
            # Try broader: any checkbox with required
            checkbox_names = re.findall(r'name="([^"]+)"[^>]*type="checkbox"[^>]*(?:required|data-valid[^>]*required)', order_html)

        # Build order form data
        order_data = {
            "payment": payment_id,
            "delivery": delivery_id,
            "finish": "1",
        }
        for cb in checkbox_names:
            order_data[cb] = "1"

        # Also add common Sky-Shop order fields
        order_data["comment"] = ""

        # Submit order
        try:
            async with session.post(
                f"{SHOP_URL}/order",
                data=order_data,
                proxy=PROXY,
                timeout=aiohttp.ClientTimeout(total=15),
                allow_redirects=True,
            ) as resp:
                final_html = await resp.text()
                final_url = str(resp.url)
                total_time = time.time() - t0
        except Exception as e:
            log.error(f"[{email}] Order submit error: {e}")
            return False

    # === CHECK RESULT ===
    success = False
    if any(kw in final_url.lower() for kw in ["potwierdzenie", "thank", "tpay", "blik", "przelewy24"]):
        success = True
    elif any(kw in final_html.lower() for kw in ["zamówienie zostało złożone", "dziękujemy", "potwierdzenie"]):
        success = True
    elif "order" not in final_url.lower() and resp.status in (200, 301, 302):
        # Redirected away from /order = likely success (to payment gateway)
        success = True

    if success:
        log.info(f"[{email}] ✅ ORDER PLACED in {total_time:.2f}s! Redirect: {final_url}")
        _mark_completed(product_id, email)
        return True
    else:
        log.error(f"[{email}] ❌ Order unclear ({total_time:.2f}s). URL: {final_url}")
        # Check for errors
        errors = re.findall(r'class="[^"]*error[^"]*"[^>]*>([^<]+)', final_html)
        if errors:
            log.error(f"[{email}] Errors: {errors[:3]}")
        return False


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


# ============================================================
# DISCORD NOTIFICATION
# ============================================================

async def _send_discord(msg):
    try:
        if not WEBHOOK_FILE.exists():
            return
        wh = WEBHOOK_FILE.read_text().strip()
        if not wh:
            return
        async with aiohttp.ClientSession() as s:
            await s.post(wh, json={"content": msg})
    except:
        pass


# ============================================================
# MAIN — FIRE TORPEDO
# ============================================================

async def fire(product_id, product_url="", accounts_count=4):
    """
    Fire torpedo on all accounts in PARALLEL.
    Total time target: <2 seconds for all 4 accounts.
    """
    t0 = time.time()
    accounts = ACCOUNTS[:accounts_count]

    log.info(f"=== TORPEDO FIRE: product {product_id}, {len(accounts)} accounts ===")
    await _send_discord(f"🚀 **TORPEDO FIRE** product {product_id} — {len(accounts)} accounts, target <2s")

    # Fire ALL accounts simultaneously
    tasks = [torpedo_buy(acc, product_id, product_url) for acc in accounts]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    total_time = time.time() - t0
    ok = sum(1 for r in results if r is True)
    failed = sum(1 for r in results if r is False or isinstance(r, Exception))

    log.info(f"=== TORPEDO DONE: {ok}/{len(accounts)} success in {total_time:.2f}s ===")

    # Discord summary
    status = "✅" if ok > 0 else "❌"
    await _send_discord(
        f"{status} **TORPEDO RESULT** product {product_id}\n"
        f"Success: {ok}/{len(accounts)} | Time: {total_time:.2f}s\n"
        f"URL: {product_url or f'{SHOP_URL}/-p{product_id}'}"
    )

    return ok


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="JC Torpedo — instant HTTP buy")
    parser.add_argument("action", choices=["fire", "warmup"], help="fire=buy now, warmup=pre-login sessions")
    parser.add_argument("--product-id", "-p", help="Product ID to buy")
    parser.add_argument("--url", "-u", default="", help="Product URL")
    parser.add_argument("--accounts", type=int, default=4, help="Number of accounts (1-4)")
    args = parser.parse_args()

    if args.action == "warmup":
        await warmup_all()
    elif args.action == "fire":
        if not args.product_id:
            print("ERROR: --product-id required for fire")
            sys.exit(1)
        ok = await fire(args.product_id, args.url, args.accounts)
        sys.exit(0 if ok > 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
