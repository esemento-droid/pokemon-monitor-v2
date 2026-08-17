#!/usr/bin/env python3
"""
Session Warmer — keeps bot accounts logged in with fresh cookies.

Runs via cron every hour. For each account × shop:
  1. Opens browser with proxy
  2. Logs in
  3. Saves cookies to JSON file
  4. Closes browser

On drop, bots load cookies instead of logging in (saves 15-20s per account).

Usage:
    # Cron (every hour):
    */60 * * * * cd /opt/pokemon-monitor-v2 && DISPLAY=:99 ./venv/bin/python3 session_warmer.py

    # In bot:
    from session_warmer import load_cookies, has_fresh_cookies
    if has_fresh_cookies('tcgumisia', email):
        cookies = load_cookies('tcgumisia', email)
        await context.add_cookies(cookies)
    else:
        await login(page, email, password)
"""
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

log = logging.getLogger("session_warmer")

BASE_DIR = Path("/opt/pokemon-monitor-v2")
COOKIES_DIR = BASE_DIR / "data" / "cookies"
COOKIES_DIR.mkdir(parents=True, exist_ok=True)

# Max age of cookies before considered stale (seconds)
MAX_COOKIE_AGE = 3600 * 2  # 2 hours

# Shop login configs
SHOPS = {
    "tcgumisia": {
        "url": "https://tcgumisia.pl",
        "login_fn": "_login_sellingo",
    },
    "japancollectibles": {
        "url": "https://japancollectibles.shop",
        "login_fn": "_login_skyshop",
    },
    "kartexpol": {
        "url": "https://kartexpol.pl",
        "login_fn": "_login_shoper",
    },
    "strefatcg": {
        "url": "https://strefatcg.pl",
        "login_fn": "_login_shoper",
    },
}

ACCOUNTS = [
    {"email": "blackmat36@gmail.com", "password_tcg": "v2@pvDGt#ZuN3ui", "password_jc": "v2@pvDGt#ZuN3ui", "password_kart": "v2@pvDGt#ZuN3ui", "password_strefa": "v2@pvDGt#ZuN3ui"},
    {"email": "tjbtaniojuzbylo@gmail.com", "password_tcg": "P9XAfQE.SCwFq5i", "password_jc": "P9XAfQE.SCwFq5i", "password_kart": "P9XAfQE.SCwFq5i", "password_strefa": "P9XAfQE.SCwFq5i"},
    {"email": "y24015411@gmail.com", "password_tcg": "huw!e.twdCmv9@B", "password_jc": "huw!e.twdCmv9@B", "password_kart": "huw!e.twdCmv9@B", "password_strefa": "huw!e.twdCmv9@B"},
    {"email": "esemento@gmail.com", "password_tcg": "cR!9GW#x2wqJtGw", "password_jc": "cR!9GW#x2wqJtGw", "password_kart": "cR!9GW#x2wqJtGw", "password_strefa": "cR!9GW#x2wqJtGw"},
]


def _cookie_path(shop: str, email: str) -> Path:
    """Get cookie file path for shop+email."""
    safe_email = email.split("@")[0]
    return COOKIES_DIR / f"{shop}_{safe_email}.json"


def load_cookies(shop: str, email: str) -> Optional[List[dict]]:
    """Load saved cookies for shop+email. Returns None if stale/missing."""
    path = _cookie_path(shop, email)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        saved_at = data.get("saved_at", 0)
        if time.time() - saved_at > MAX_COOKIE_AGE:
            return None  # Too old
        return data.get("cookies", [])
    except Exception:
        return None


def has_fresh_cookies(shop: str, email: str) -> bool:
    """Check if we have fresh (< 2h old) cookies for this account."""
    return load_cookies(shop, email) is not None


def save_cookies(shop: str, email: str, cookies: List[dict]):
    """Save cookies to file."""
    path = _cookie_path(shop, email)
    data = {
        "shop": shop,
        "email": email,
        "saved_at": time.time(),
        "saved_at_human": time.strftime("%Y-%m-%d %H:%M:%S"),
        "cookies": cookies,
    }
    path.write_text(json.dumps(data, indent=2))
    log.info(f"[{shop}] Cookies saved for {email} ({len(cookies)} cookies)")


async def _warm_sellingo(shop_url: str, email: str, password: str, proxy: Optional[dict]) -> Optional[List[dict]]:
    """Login to Sellingo shop and return cookies."""
    from patchright.async_api import async_playwright
    from bot_utils import wait_for_verification

    async with async_playwright() as p:
        launch_args = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        if proxy:
            launch_args["proxy"] = proxy

        browser = await p.chromium.launch(**launch_args)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        try:
            await page.goto(shop_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)
            await wait_for_verification(page)

            # Accept cookies
            try:
                btn = page.locator('.js-accept-cookie-alert-1')
                if await btn.count() > 0:
                    await btn.click(timeout=3000)
            except Exception:
                pass

            # Open login modal
            try:
                konto_btn = page.locator('button[data-aside-target="modal-aside-entry-form"]')
                await konto_btn.click(timeout=5000)
            except Exception:
                await page.evaluate("""() => {
                    const btn = document.querySelector('button[data-aside-target="modal-aside-entry-form"]');
                    if (btn) btn.click();
                }""")
            await asyncio.sleep(2)

            # Fill login
            email_input = page.locator('.js-login-form input[type="email"]').first
            pass_input = page.locator('.js-login-form input[type="password"]').first
            await email_input.fill(email)
            await asyncio.sleep(0.3)
            await pass_input.fill(password)
            await asyncio.sleep(0.3)

            # Submit
            await page.locator('.js-submit-login').click(timeout=5000)
            await asyncio.sleep(5)
            await wait_for_verification(page)

            # Get cookies
            cookies = await context.cookies()
            await browser.close()
            return cookies if cookies else None

        except Exception as e:
            log.error(f"Sellingo warm failed: {e}")
            await browser.close()
            return None


async def _warm_skyshop(shop_url: str, email: str, password: str, proxy: Optional[dict]) -> Optional[List[dict]]:
    """Login to Sky-Shop (japancollectibles) and return cookies."""
    from patchright.async_api import async_playwright

    async with async_playwright() as p:
        launch_args = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        if proxy:
            launch_args["proxy"] = proxy

        browser = await p.chromium.launch(**launch_args)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        try:
            await page.goto(f"{shop_url}/login", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)

            # Dismiss overlays
            await page.evaluate("""() => {
                document.getElementById('cc--main')?.remove();
                document.querySelector('.skyshop-alert-conditional-access button')?.click();
            }""")
            await asyncio.sleep(1)

            # Login
            await page.fill("input#email", email)
            await page.fill("input[name='password']", password)
            await page.click("button[name='submit']", force=True)
            await asyncio.sleep(4)

            cookies = await context.cookies()
            await browser.close()
            return cookies if cookies else None

        except Exception as e:
            log.error(f"SkyShop warm failed: {e}")
            await browser.close()
            return None


async def _warm_shoper(shop_url: str, email: str, password: str, proxy: Optional[dict]) -> Optional[List[dict]]:
    """Login to Shoper shop and return cookies."""
    from patchright.async_api import async_playwright

    async with async_playwright() as p:
        launch_args = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        if proxy:
            launch_args["proxy"] = proxy

        browser = await p.chromium.launch(**launch_args)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        try:
            await page.goto(f"{shop_url}/pl/login", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)

            await page.fill("input[name='email'], input#email", email)
            await page.fill("input[name='password'], input#password", password)
            await page.click("button[type='submit'], input[type='submit']", force=True)
            await asyncio.sleep(5)

            cookies = await context.cookies()
            await browser.close()
            return cookies if cookies else None

        except Exception as e:
            log.error(f"Shoper warm failed: {e}")
            await browser.close()
            return None


async def warm_all():
    """Warm all accounts on all shops. Hard timeout per account to prevent hangs."""
    from proxy_router import get_playwright_proxy

    results = {"ok": 0, "fail": 0}

    for shop_name, shop_config in SHOPS.items():
        shop_url = shop_config["url"]
        login_fn_name = shop_config["login_fn"]

        # Pick warm function
        if login_fn_name == "_login_sellingo":
            warm_fn = _warm_sellingo
        elif login_fn_name == "_login_skyshop":
            warm_fn = _warm_skyshop
        elif login_fn_name == "_login_shoper":
            warm_fn = _warm_shoper
        else:
            continue

        for account in ACCOUNTS:
            email = account["email"]
            # Get password for this shop
            pw_key = f"password_{shop_name[:4]}"
            password = account.get(pw_key, account.get("password_tcg", ""))

            # Skip if cookies still fresh
            if has_fresh_cookies(shop_name, email):
                continue

            # Get proxy for this account
            proxy = get_playwright_proxy(shop_name, email)

            log.info(f"[{shop_name}] Warming {email}...")
            try:
                # Hard 60s timeout per account — prevents infinite hangs
                cookies = await asyncio.wait_for(
                    warm_fn(shop_url, email, password, proxy),
                    timeout=60
                )
                if cookies:
                    save_cookies(shop_name, email, cookies)
                    results["ok"] += 1
                else:
                    log.warning(f"[{shop_name}] No cookies for {email}")
                    results["fail"] += 1
            except asyncio.TimeoutError:
                log.error(f"[{shop_name}] TIMEOUT warming {email} (60s)")
                results["fail"] += 1
            except Exception as e:
                log.error(f"[{shop_name}] Warm error {email}: {e}")
                results["fail"] += 1

            # Delay between accounts
            await asyncio.sleep(5)

    log.info(f"Warming complete: {results['ok']} OK, {results['fail']} FAIL")
    return results


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [WARMER] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(BASE_DIR / "session_warmer.log", mode="a"),
        ],
    )
    asyncio.run(warm_all())
