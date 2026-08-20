"""
CF Solver — lightweight FlareSolverr replacement.

DUAL-PATH ARCHITECTURE (2026-08-20):
- PRIMARY: patchright headless=False + mobile proxy (works for 5/7 CF shops)
- FALLBACK: patchright headless=False WITHOUT proxy (VPS IP) for stubborn shops
  CF blocks mobile IP on gralnia/xjoy but datacenter IP + good fingerprint can pass.

KEY INSIGHTS from research (Theyka/Turnstile-Solver, EzSolver, scrapfly.io):
1. headless=False is MANDATORY (Turnstile detects headless)
2. Fresh context per solve (cookie poisoning = instant fail)
3. Human-like mouse click (coordinates + jitter, not element.click())
4. VPS IP may pass where residential fails (IP reputation per-domain)
5. Timeout 45s+ for Turnstile (CF docs say "at least 60s" for challenge solve)

RESOURCE: 2 browsers × ~100MB each = ~200MB idle. Pages ~60MB each, freed after solve.
"""
import asyncio
import logging
import os
import random
import time

logger = logging.getLogger("monitor")

PROXY_ADDR = os.environ.get("PROXY_ADDR", "127.0.0.1:8888")
MAX_CONCURRENT = 4   # Max simultaneous CF solves (shared across both browsers)
SOLVE_TIMEOUT = 55   # Max seconds for entire solve
CF_WAIT_MAX = 40     # Max seconds to wait for CF challenge (was 30, CF docs say 60s)
TURNSTILE_CLICK_AT = [2, 5, 8, 12, 18, 25, 32]  # Seconds at which to attempt click

# Shops that consistently fail on mobile proxy → try VPS IP first
VPS_FIRST_SHOPS = {"gralnia", "xjoy"}

_browser_proxy = None     # Browser with mobile proxy
_browser_direct = None    # Browser without proxy (VPS IP)
_pw = None
_semaphore = None
_lock = asyncio.Lock()
_started = False
_consecutive_fails = 0

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


async def _ensure_browsers():
    """Start both browsers if not running. headless=False + Xvfb."""
    global _browser_proxy, _browser_direct, _pw, _semaphore, _started

    if _started and _browser_proxy and _browser_proxy.is_connected():
        return

    async with _lock:
        if _started and _browser_proxy and _browser_proxy.is_connected():
            return

        logger.info("[CF_SOLVER] Starting dual browsers (headless=False, DISPLAY=%s)...",
                    os.environ.get("DISPLAY", "not set"))
        from patchright.async_api import async_playwright
        _pw = await async_playwright().start()

        # Browser 1: with mobile proxy (for most CF shops)
        _browser_proxy = await _pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--disable-background-timer-throttling",
                "--window-size=1920,1080",
                f"--proxy-server=http://{PROXY_ADDR}",
            ]
        )

        # Browser 2: NO proxy (VPS IP) — fallback for shops that block mobile IP
        _browser_direct = await _pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--disable-background-timer-throttling",
                "--window-size=1920,1080",
            ]
        )

        _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        _started = True
        logger.info("[CF_SOLVER] Dual browsers ready (proxy + direct, concurrent=%d)", MAX_CONCURRENT)


async def _restart_browsers():
    """Full restart — nuclear option."""
    global _browser_proxy, _browser_direct, _pw, _started, _consecutive_fails
    logger.warning("[CF_SOLVER] FULL RESTART — %d consecutive failures", _consecutive_fails)
    for b in [_browser_proxy, _browser_direct]:
        if b:
            try:
                await b.close()
            except Exception:
                pass
    _browser_proxy = None
    _browser_direct = None
    if _pw:
        try:
            await _pw.stop()
        except Exception:
            pass
    _pw = None
    _started = False
    _consecutive_fails = 0
    await _ensure_browsers()


async def _human_click_turnstile(page, wait_sec):
    """
    Human-like Turnstile click based on EzSolver approach:
    - Find Turnstile iframe bounding box
    - Move mouse with jitter to checkbox position
    - Click at coordinates (not element.click() which is detectable)
    """
    if wait_sec not in TURNSTILE_CLICK_AT:
        return False

    try:
        # Find the Turnstile iframe bounding box
        iframe_rect = await page.evaluate("""
            (() => {
                for (const f of document.querySelectorAll('iframe')) {
                    const src = f.src || f.getAttribute('src') || '';
                    if (!src.includes('challenges.cloudflare.com')) continue;
                    const r = f.getBoundingClientRect();
                    if (r.width > 20 && r.height > 20)
                        return {x: r.x, y: r.y, w: r.width, h: r.height};
                }
                // Also check .cf-turnstile div
                const div = document.querySelector('.cf-turnstile, [class*="cf-turnstile"]');
                if (div) {
                    const r = div.getBoundingClientRect();
                    if (r.width > 20 && r.height > 20)
                        return {x: r.x, y: r.y, w: r.width, h: r.height};
                }
                return null;
            })()
        """)

        if iframe_rect:
            # Checkbox is typically at left side of iframe, ~28px in, vertically centered
            cx = iframe_rect["x"] + 28 + random.uniform(-4, 4)
            cy = iframe_rect["y"] + iframe_rect["h"] / 2 + random.uniform(-4, 4)

            # Human-like: move to nearby first, then to target
            pre_x = cx + random.uniform(-60, -20)
            pre_y = cy + random.uniform(-30, 30)
            await page.mouse.move(pre_x, pre_y)
            await asyncio.sleep(random.uniform(0.1, 0.25))
            await page.mouse.move(cx, cy)
            await asyncio.sleep(random.uniform(0.05, 0.15))
            await page.mouse.click(cx, cy)

            logger.info(f"[CF_SOLVER] Human-click Turnstile at ({cx:.0f}, {cy:.0f})")
            await asyncio.sleep(random.uniform(1.5, 2.5))
            return True
    except Exception as e:
        pass

    # Fallback: try direct element click on iframe content
    try:
        for frame in page.frames:
            frame_url = frame.url or ""
            if "challenges.cloudflare.com" in frame_url:
                for selector in ["input[type='checkbox']", ".cb-i", "body"]:
                    try:
                        el = await frame.query_selector(selector)
                        if el:
                            await el.click()
                            logger.info(f"[CF_SOLVER] Fallback click: {selector}")
                            await asyncio.sleep(1)
                            return True
                    except Exception:
                        continue
    except Exception:
        pass

    return False


async def _solve_with_browser(browser, url, timeout, label="proxy"):
    """Core solve logic for a single browser instance."""
    context = None
    page = None

    try:
        context = await browser.new_context(
            user_agent=UA,
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        # Navigate
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)

        # Wait for CF challenge to resolve
        resolved = False
        for wait_sec in range(CF_WAIT_MAX):
            title = await page.title()
            content_check = await page.evaluate(
                "() => document.body ? document.body.innerText.substring(0, 200) : ''"
            )

            title_lower = (title or "").lower()
            content_lower = (content_check or "").lower()

            is_challenge = (
                any(x in title_lower for x in ["moment", "checking", "attention", "just a moment"]) or
                any(x in content_lower for x in ["verif", "checking your browser", "please wait",
                                                  "enable javascript", "ray id"])
            )

            if not is_challenge:
                resolved = True
                break

            # Human-like Turnstile click
            await _human_click_turnstile(page, wait_sec)
            await asyncio.sleep(1)

        if not resolved:
            logger.warning(f"[CF_SOLVER] [{label}] Not resolved: {url[:55]} after {CF_WAIT_MAX}s")
            return None

        html = await page.content()
        if not html or len(html) < 500:
            logger.warning(f"[CF_SOLVER] [{label}] Empty: {url[:55]} ({len(html or '')} chars)")
            return None

        logger.info(f"[CF_SOLVER] [{label}] Solved OK: {url[:50]} ({len(html)} chars)")
        return html

    except asyncio.TimeoutError:
        logger.warning(f"[CF_SOLVER] [{label}] Timeout {timeout}s: {url[:55]}")
        return None
    except Exception as e:
        err_str = str(e)
        if "ERR_PROXY" in err_str or "Connect call failed" in err_str:
            logger.warning(f"[CF_SOLVER] [{label}] Proxy fail: {url[:55]}")
        else:
            logger.error(f"[CF_SOLVER] [{label}] Error: {url[:55]}: {err_str[:80]}")
        return None
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass


def _get_shop_from_url(url):
    """Extract shop hint from URL for routing decisions."""
    url_lower = url.lower()
    if "gralnia" in url_lower:
        return "gralnia"
    if "xjoy" in url_lower:
        return "xjoy"
    if "battlestash" in url_lower:
        return "battlestash"
    if "sklepkleks" in url_lower:
        return "sklepkleks"
    if "dystryktzero" in url_lower:
        return "dystryktzero"
    if "mepel" in url_lower:
        return "mepel"
    if "tcg-zielona" in url_lower or "tcgzielona" in url_lower:
        return "tcgzielona"
    return "unknown"


async def solve(url, timeout=SOLVE_TIMEOUT, session_name=None):
    """
    Dual-path Cloudflare challenge solver.

    Strategy:
    - For most shops: try proxy browser first (mobile IP = residential trust)
    - For VPS_FIRST_SHOPS (gralnia, xjoy): try VPS IP first (mobile IP is blacklisted there)
    - If primary fails: try fallback path
    - Result: every shop has 2 chances with different IPs
    """
    await _ensure_browsers()

    global _consecutive_fails

    async with _semaphore:
        shop = _get_shop_from_url(url)

        # Determine order: which browser to try first
        if shop in VPS_FIRST_SHOPS:
            browsers = [
                (_browser_direct, "direct"),
                (_browser_proxy, "proxy"),
            ]
        else:
            browsers = [
                (_browser_proxy, "proxy"),
                (_browser_direct, "direct"),
            ]

        for browser, label in browsers:
            if not browser or not browser.is_connected():
                continue

            html = await _solve_with_browser(browser, url, timeout, label)

            if html:
                _consecutive_fails = 0
                return html

        # Both paths failed
        _consecutive_fails += 1
        if _consecutive_fails >= 30:
            asyncio.ensure_future(_restart_browsers())

        return None


async def solve_fs_compat(url, max_timeout=30000, session=None):
    """
    FlareSolverr-compatible interface.
    Returns dict like FS: {"status": "ok", "solution": {"response": html}}
    """
    timeout_s = max_timeout / 1000 if max_timeout > 100 else max_timeout
    html = await solve(url, timeout=timeout_s)

    if html:
        return {
            "status": "ok",
            "solution": {
                "response": html,
                "status": 200,
                "url": url,
            }
        }
    else:
        return {
            "status": "error",
            "message": f"Challenge not solved for {url[:60]}",
            "solution": {"response": ""},
        }


async def close():
    """Shutdown both browsers."""
    global _browser_proxy, _browser_direct, _pw, _started, _consecutive_fails
    _consecutive_fails = 0
    for b in [_browser_proxy, _browser_direct]:
        if b:
            try:
                await b.close()
            except Exception:
                pass
    _browser_proxy = None
    _browser_direct = None
    if _pw:
        try:
            await _pw.stop()
        except Exception:
            pass
    _pw = None
    _started = False
    logger.info("[CF_SOLVER] Closed")
