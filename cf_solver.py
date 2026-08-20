"""
CF Solver — lightweight FlareSolverr replacement.

Uses persistent patchright browser (stealth, anti-detection) to solve
Cloudflare challenges and return page HTML.

KEY INSIGHT (2026-08-20): headless=True is DETECTED by Turnstile.
Must use headless=False + DISPLAY=:99 (Xvfb). This is what all working
Turnstile solvers do (Theyka/Turnstile-Solver, turnaround, etc.)

ARCHITECTURE:
- 1 browser process (headless=False via Xvfb DISPLAY=:99)
- Fresh context per solve (avoids cookie poisoning from failed attempts)
- Semaphore limits concurrency
- Turnstile resolution: wait for page → click cf-turnstile div → wait for resolve
- Auto browser restart after consecutive failures

RESOURCE USAGE:
- 1 browser, fresh context per request (closed after)
- Max 4 concurrent solves (semaphore)
- ~60MB per active page (freed after solve)
- headless=False on Xvfb = same RAM as headless (no real display)
"""
import asyncio
import logging
import os
import time

logger = logging.getLogger("monitor")

PROXY_ADDR = os.environ.get("PROXY_ADDR", "127.0.0.1:8888")
MAX_CONCURRENT = 4   # Max simultaneous CF solves
SOLVE_TIMEOUT = 50   # Max seconds for entire solve
CF_WAIT_MAX = 30     # Max seconds to wait for CF challenge resolution
TURNSTILE_CLICK_ATTEMPTS = [2, 5, 10, 15, 20, 25]  # Seconds at which to attempt click

_browser = None
_pw = None
_semaphore = None
_lock = asyncio.Lock()
_started = False
_consecutive_fails = 0

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


async def _ensure_browser():
    """Start patchright browser if not running. headless=False is CRITICAL for Turnstile."""
    global _browser, _pw, _semaphore, _started

    if _started and _browser and _browser.is_connected():
        return

    async with _lock:
        if _started and _browser and _browser.is_connected():
            return

        logger.info("[CF_SOLVER] Starting patchright browser (headless=False, DISPLAY=%s)...",
                    os.environ.get("DISPLAY", "not set"))
        from patchright.async_api import async_playwright
        _pw = await async_playwright().start()
        _browser = await _pw.chromium.launch(
            headless=False,  # CRITICAL: Turnstile detects headless=True and refuses to solve
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
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        _started = True
        logger.info("[CF_SOLVER] Browser ready (patchright headless=False + proxy, concurrent=%d)", MAX_CONCURRENT)


async def _restart_browser():
    """Full browser restart — nuclear option when all contexts are failing."""
    global _browser, _pw, _started, _consecutive_fails
    logger.warning("[CF_SOLVER] FULL RESTART — too many consecutive failures (%d)", _consecutive_fails)
    if _browser:
        try:
            await _browser.close()
        except Exception:
            pass
    if _pw:
        try:
            await _pw.stop()
        except Exception:
            pass
    _started = False
    _consecutive_fails = 0
    # Re-create
    await _ensure_browser()


async def _try_click_turnstile(page, wait_sec):
    """
    Attempt to click Turnstile widget. Based on Theyka/Turnstile-Solver approach:
    - Look for .cf-turnstile div and click it
    - Look for Turnstile iframe and click inside
    - Check cf-turnstile-response input for solve token
    """
    if wait_sec not in TURNSTILE_CLICK_ATTEMPTS:
        return False

    try:
        # Method 1: Click the .cf-turnstile div directly (most common)
        turnstile_div = await page.query_selector(".cf-turnstile, [class*='cf-turnstile']")
        if turnstile_div:
            await turnstile_div.click()
            logger.info(f"[CF_SOLVER] Clicked .cf-turnstile div")
            await asyncio.sleep(1)
            return True
    except Exception:
        pass

    try:
        # Method 2: Find Turnstile iframe and click inside it
        for frame in page.frames:
            frame_url = frame.url or ""
            if "challenges.cloudflare.com" in frame_url or "turnstile" in frame_url:
                # Try multiple selectors inside the iframe
                for selector in ["input[type='checkbox']", ".cb-i", "#challenge-stage",
                                 "body", "[id*='challenge']"]:
                    try:
                        el = await frame.query_selector(selector)
                        if el:
                            bbox = await el.bounding_box()
                            if bbox:
                                await frame.click(selector)
                                logger.info(f"[CF_SOLVER] Clicked Turnstile iframe element: {selector}")
                                await asyncio.sleep(1)
                                return True
                    except Exception:
                        continue
    except Exception:
        pass

    return False


async def solve(url, timeout=SOLVE_TIMEOUT, session_name=None):
    """
    Solve Cloudflare challenge and return page HTML.

    Strategy (based on research of working Turnstile solvers 2026):
    1. headless=False (Turnstile DETECTS headless)
    2. Fresh context per request (no cookie poisoning)
    3. Navigate to URL
    4. Wait for CF to auto-resolve OR click Turnstile widget
    5. Return page HTML
    """
    await _ensure_browser()

    global _consecutive_fails

    async with _semaphore:
        context = None
        page = None

        # Retry once on proxy failure
        for attempt in range(2):
            try:
                # Fresh context per solve — critical for avoiding cookie poisoning
                # (Theyka solver also creates new context per solve)
                context = await _browser.new_context(
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

                    # CF challenge indicators
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

                    # Attempt Turnstile click at specific intervals
                    await _try_click_turnstile(page, wait_sec)

                    await asyncio.sleep(1)

                if not resolved:
                    logger.warning(f"[CF_SOLVER] Challenge not resolved for {url[:60]} after {CF_WAIT_MAX}s")
                    _consecutive_fails += 1
                    if _consecutive_fails >= 20:
                        asyncio.ensure_future(_restart_browser())
                    return None

                # Get full HTML
                html = await page.content()

                if not html or len(html) < 500:
                    logger.warning(f"[CF_SOLVER] Empty/short response for {url[:60]} ({len(html or '')} chars)")
                    _consecutive_fails += 1
                    return None

                # Success! Reset failure counter
                _consecutive_fails = 0
                logger.info(f"[CF_SOLVER] Solved OK for {url[:50]} ({len(html)} chars)")
                return html

            except asyncio.TimeoutError:
                logger.warning(f"[CF_SOLVER] Timeout {timeout}s for {url[:60]}")
                _consecutive_fails += 1
                return None
            except Exception as e:
                err_str = str(e)
                # Retry on proxy connection failure (brief tunnel hiccup)
                if ("ERR_PROXY" in err_str or "Connect call failed" in err_str) and attempt == 0:
                    logger.warning(f"[CF_SOLVER] Proxy fail for {url[:60]}, retry in 3s...")
                    # Close current context before retry
                    if context:
                        try:
                            await context.close()
                        except Exception:
                            pass
                        context = None
                    await asyncio.sleep(3)
                    continue

                if "ERR_PROXY" in err_str or "Connect call failed" in err_str:
                    logger.error(f"[CF_SOLVER] Proxy fail AGAIN for {url[:60]}")
                else:
                    logger.error(f"[CF_SOLVER] Error for {url[:60]}: {err_str[:100]}")

                # If browser itself is dead
                if "closed" in err_str.lower() or "crash" in err_str.lower() or "target page" in err_str.lower():
                    logger.warning(f"[CF_SOLVER] Browser may be dead, marking for restart")
                    global _started
                    _started = False

                _consecutive_fails += 1
                return None
            finally:
                # Always close context (fresh per request — no accumulation)
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass


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
    """Shutdown browser."""
    global _browser, _pw, _started, _consecutive_fails
    _consecutive_fails = 0
    if _browser:
        try:
            await _browser.close()
        except Exception:
            pass
    if _pw:
        try:
            await _pw.stop()
        except Exception:
            pass
    _started = False
    logger.info("[CF_SOLVER] Closed")
