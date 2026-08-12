"""
Bot Engine — shared logic for all autobuy bots.

Provides:
  - Delay humanizer (random timing + fingerprint rotation)
  - Retry logic (proxy fail → switch, ATC fail → retry, cart empty → wait)
  - Pre-warmed session loading
  - Smart proxy per account
  - Standard browser launch with all protections

Usage in bot:
    from bot_engine import BotEngine

    engine = BotEngine(shop="tcgumisia")
    
    for account in accounts:
        async with engine.session(account) as (page, proxy_info):
            # page is ready — logged in (from cookies or fresh login)
            await do_atc(page, product_url)
            await engine.retry_on_fail(do_checkout, page, max_retries=3)
"""
import asyncio
import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Optional, Dict, Callable, Any

log = logging.getLogger("bot_engine")

BASE_DIR = Path("/opt/pokemon-monitor-v2")

# === HUMANIZER CONFIG ===
# Delays between accounts (seconds) — randomized to avoid detection
INTER_ACCOUNT_DELAY = (12, 25)  # min, max seconds between accounts
INTER_ACTION_DELAY = (0.5, 2.0)  # min, max between page actions
POST_ATC_DELAY = (2, 5)  # after add-to-cart
POST_LOGIN_DELAY = (2, 4)  # after login

# Fingerprint pool — rotate per account
VIEWPORTS = [
    {"width": 1280, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

LOCALES = ["pl-PL", "pl", "en-PL"]
TIMEZONES = ["Europe/Warsaw"]


class BotEngine:
    """Shared bot engine with humanizer, retry, proxy routing."""

    def __init__(self, shop: str, webhook_file: Optional[str] = None):
        self.shop = shop
        self.webhook_file = webhook_file
        self._account_index = 0

    def get_fingerprint(self, account_index: int = 0) -> Dict:
        """Get unique fingerprint for this account (viewport, UA, locale)."""
        idx = account_index % len(VIEWPORTS)
        return {
            "viewport": VIEWPORTS[idx],
            "user_agent": USER_AGENTS[idx % len(USER_AGENTS)],
            "locale": LOCALES[idx % len(LOCALES)],
            "timezone_id": TIMEZONES[0],
        }

    def get_proxy(self, account_email: str) -> Optional[Dict]:
        """Get proxy for this account via router."""
        try:
            from proxy_router import get_playwright_proxy
            return get_playwright_proxy(self.shop, account_email)
        except ImportError:
            # Fallback
            import subprocess
            try:
                r = subprocess.run(
                    ["curl", "-x", "http://127.0.0.1:8888", "-s", "-o", "/dev/null",
                     "-w", "%{http_code}", "--connect-timeout", "3", "https://google.com"],
                    capture_output=True, text=True, timeout=5
                )
                if r.stdout.strip() in ("200", "301"):
                    return {"server": "http://127.0.0.1:8888"}
            except Exception:
                pass
            return None

    async def human_delay(self, delay_type: str = "action"):
        """Random delay to appear human."""
        ranges = {
            "action": INTER_ACTION_DELAY,
            "account": INTER_ACCOUNT_DELAY,
            "atc": POST_ATC_DELAY,
            "login": POST_LOGIN_DELAY,
        }
        min_d, max_d = ranges.get(delay_type, INTER_ACTION_DELAY)
        delay = random.uniform(min_d, max_d)
        await asyncio.sleep(delay)

    async def retry_on_fail(self, fn: Callable, *args, max_retries: int = 3,
                            retry_delay: float = 5.0, **kwargs) -> Any:
        """
        Retry a function on failure with exponential backoff.
        If proxy-related error → switch proxy and retry.
        """
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                result = await fn(*args, **kwargs)
                return result
            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Proxy-related errors — can't recover in same session
                if any(kw in error_str for kw in [
                    "proxy", "err_proxy", "connection_refused", "tunnel"
                ]):
                    log.warning(f"[{self.shop}] Proxy error on attempt {attempt}: {e}")
                    # Invalidate proxy
                    try:
                        from proxy_router import invalidate_proxy
                        invalidate_proxy("mobile_tunnel")
                    except ImportError:
                        pass
                    raise  # Can't retry with same browser

                # Timeout / network — wait and retry
                if any(kw in error_str for kw in ["timeout", "navigation", "net::"]):
                    wait = retry_delay * attempt
                    log.warning(f"[{self.shop}] Attempt {attempt}/{max_retries} failed (timeout), retry in {wait}s")
                    await asyncio.sleep(wait)
                    continue

                # ATC-specific: cart might be empty due to rate limit
                if any(kw in error_str for kw in ["cart", "koszyk", "empty"]):
                    wait = retry_delay * attempt * 2
                    log.warning(f"[{self.shop}] Cart issue on attempt {attempt}, retry in {wait}s")
                    await asyncio.sleep(wait)
                    continue

                # Unknown error — retry with backoff
                wait = retry_delay * attempt
                log.warning(f"[{self.shop}] Attempt {attempt}/{max_retries}: {e}, retry in {wait}s")
                await asyncio.sleep(wait)

        log.error(f"[{self.shop}] All {max_retries} retries failed: {last_error}")
        raise last_error

    def load_cookies(self, email: str) -> Optional[list]:
        """Load pre-warmed cookies for this shop+account."""
        try:
            from session_warmer import load_cookies as _load
            return _load(self.shop, email)
        except ImportError:
            # Direct load
            safe_email = email.split("@")[0]
            path = BASE_DIR / "data" / "cookies" / f"{self.shop}_{safe_email}.json"
            if not path.exists():
                return None
            try:
                data = json.loads(path.read_text())
                if time.time() - data.get("saved_at", 0) > 7200:
                    return None
                return data.get("cookies")
            except Exception:
                return None

    async def launch_browser(self, account_email: str, account_index: int = 0,
                             headless: bool = False):
        """
        Launch browser with proxy + fingerprint for this account.
        Returns (playwright, browser, context, page).
        Caller must close browser when done.
        """
        from patchright.async_api import async_playwright

        fp = self.get_fingerprint(account_index)
        proxy = self.get_proxy(account_email)

        p = await async_playwright().start()

        launch_args = {
            "headless": headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        }
        if proxy:
            launch_args["proxy"] = proxy
            log.info(f"[{account_email}] Proxy: {proxy['server']}")
        else:
            log.info(f"[{account_email}] Proxy: DIRECT")

        browser = await p.chromium.launch(**launch_args)
        context = await browser.new_context(
            viewport=fp["viewport"],
            user_agent=fp["user_agent"],
            locale=fp["locale"],
            timezone_id=fp["timezone_id"],
        )

        # Load pre-warmed cookies if available
        cookies = self.load_cookies(account_email)
        if cookies:
            await context.add_cookies(cookies)
            log.info(f"[{account_email}] Loaded {len(cookies)} pre-warmed cookies")

        page = await context.new_page()
        return p, browser, context, page

    async def notify_discord(self, message: str):
        """Send notification to Discord."""
        try:
            wh_path = None
            if self.webhook_file:
                wh_path = Path(self.webhook_file)
            else:
                wh_path = BASE_DIR / "discord_webhook_jc.txt"

            if not wh_path or not wh_path.exists():
                return
            webhook_url = wh_path.read_text().strip()
            if not webhook_url:
                return

            import aiohttp
            async with aiohttp.ClientSession() as s:
                await s.post(webhook_url, json={"content": message}, timeout=aiohttp.ClientTimeout(total=10))
        except Exception:
            pass
