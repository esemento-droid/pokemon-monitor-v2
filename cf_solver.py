"""
CF Solver — lightweight FlareSolverr replacement.

TRI-PATH ARCHITECTURE (2026-08-21):
- PATH 1: patchright headless=False + mobile proxy (works for 6/9 CF shops)
- PATH 2: patchright headless=False WITHOUT proxy (VPS IP) — fallback
- PATH 3: Camoufox (Firefox anti-detect) + mobile proxy — for HARD_SHOPS
  Camoufox uses Firefox fingerprint (not Chromium) → CF can't detect automation.
  Used ONLY for gralnia/xjoy/battlestash where both Chromium paths fail.

KEY INSIGHTS:
1. headless=False is MANDATORY for Chromium (Turnstile detects headless)
2. Camoufox can run headless=True safely (Firefox fingerprint spoofed at C++ level)
3. Fresh context per solve (cookie poisoning = instant fail)
4. Human-like mouse click (coordinates + jitter, not element.click())
5. Different browser engine = different fingerprint = CF treats it as new user

RESOURCE: 2 Chromium browsers × ~100MB + 1 Camoufox (lazy) × ~150MB = ~350MB max.
"""
import asyncio
import logging
import os
import random
import time

logger = logging.getLogger("monitor")

PROXY_ADDR = os.environ.get("PROXY_ADDR", "127.0.0.1:8888")
MAX_CONCURRENT = 6   # Max simultaneous CF solves (Chromium browsers only)
CAMOUFOX_CONCURRENT = 2  # Separate slots for Camoufox (don't starve Chromium)
SOLVE_TIMEOUT = 55   # Max seconds for entire solve
CF_WAIT_MAX = 40     # Max seconds to wait for CF challenge (was 30, CF docs say 60s)
TURNSTILE_CLICK_AT = [2, 5, 8, 12, 18, 25, 32]  # Seconds at which to attempt click
RESTART_THRESHOLD = 15  # Restart browsers after this many consecutive failures

# Shops that consistently fail on mobile proxy → try VPS IP first
VPS_FIRST_SHOPS = {"gralnia", "xjoy"}

# Shops that need extra time (aggressive Turnstile) → use Camoufox (Firefox)
HARD_SHOPS = {"xjoy", "gralnia", "battlestash"}

_browser_proxy = None     # Browser with mobile proxy
_browser_direct = None    # Browser without proxy (VPS IP)
_camoufox_browser = None  # Camoufox (Firefox anti-detect) — lazy init for HARD_SHOPS
_pw = None
_semaphore = None
_camoufox_semaphore = None  # Separate semaphore for Camoufox (prevents starvation)
_lock = asyncio.Lock()
_started = False
_consecutive_fails = 0

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


class _BrowserDeadError(Exception):
    """Internal: signals that a browser process died and needs restart."""
    pass


async def _ensure_browsers():
    """Start both browsers if not running. headless=False + Xvfb."""
    global _browser_proxy, _browser_direct, _pw, _semaphore, _camoufox_semaphore, _started

    # Check if browsers are actually alive (not just _started flag)
    if _started:
        proxy_alive = _browser_proxy and _browser_proxy.is_connected()
        direct_alive = _browser_direct and _browser_direct.is_connected()
        if proxy_alive and direct_alive:
            return
        # At least one is dead — full restart needed
        logger.warning("[CF_SOLVER] _ensure_browsers: stale state (proxy=%s, direct=%s) — reinitializing",
                       proxy_alive, direct_alive)
        # Clean up stale references
        for b in [_browser_proxy, _browser_direct]:
            if b:
                try:
                    await asyncio.wait_for(b.close(), timeout=5)
                except Exception:
                    pass
        _browser_proxy = None
        _browser_direct = None
        if _pw:
            try:
                await asyncio.wait_for(_pw.stop(), timeout=5)
            except Exception:
                pass
        _pw = None
        _started = False

    async with _lock:
        # Double-check after lock
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

        if not _semaphore:
            _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        if not _camoufox_semaphore:
            _camoufox_semaphore = asyncio.Semaphore(CAMOUFOX_CONCURRENT)
        _started = True
        logger.info("[CF_SOLVER] Dual browsers ready (proxy + direct, concurrent=%d, camoufox_slots=%d)", MAX_CONCURRENT, CAMOUFOX_CONCURRENT)


async def _restart_browsers():
    """Full restart — nuclear option. Handles all edge cases gracefully."""
    global _browser_proxy, _browser_direct, _camoufox_browser, _pw, _started, _consecutive_fails
    logger.warning("[CF_SOLVER] FULL RESTART — %d consecutive failures", _consecutive_fails)
    
    # Close everything safely
    for b in [_browser_proxy, _browser_direct]:
        if b:
            try:
                await asyncio.wait_for(b.close(), timeout=10)
            except Exception:
                pass
    await _close_camoufox()
    _browser_proxy = None
    _browser_direct = None
    if _pw:
        try:
            await asyncio.wait_for(_pw.stop(), timeout=10)
        except Exception:
            pass
    _pw = None
    _started = False
    _consecutive_fails = 0
    
    # Wait a moment for processes to die
    await asyncio.sleep(3)
    
    # Retry browser start with backoff
    for attempt in range(3):
        try:
            await _ensure_browsers()
            logger.info("[CF_SOLVER] RESTART successful (attempt %d)", attempt + 1)
            return
        except Exception as e:
            logger.error(f"[CF_SOLVER] RESTART attempt {attempt + 1}/3 failed: {e}")
            await asyncio.sleep(5 * (attempt + 1))
    
    logger.error("[CF_SOLVER] RESTART FAILED after 3 attempts — solver will retry on next request")


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

    shop = _get_shop_from_url(url)
    # Hard shops get extended wait time
    wait_max = CF_WAIT_MAX + 15 if shop in HARD_SHOPS else CF_WAIT_MAX

    try:
        context = await browser.new_context(
            user_agent=UA,
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        # Navigate — use networkidle for hard shops (more content loading time)
        wait_until = "networkidle" if shop in HARD_SHOPS else "domcontentloaded"
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
        except Exception:
            # networkidle can timeout on slow sites — fallback, page is still usable
            pass

        # Wait for CF challenge to resolve
        resolved = False
        for wait_sec in range(wait_max):
            title = await page.title()
            content_check = await page.evaluate(
                "() => document.body ? document.body.innerText.substring(0, 200) : ''"
            )

            title_lower = (title or "").lower()
            content_lower = (content_check or "").lower()

            is_challenge = (
                any(x in title_lower for x in ["moment", "checking", "attention", "just a moment"]) or
                any(x in content_lower for x in ["verif", "checking your browser", "please wait",
                                                  "enable javascript", "ray id",
                                                  "weryfikac", "czekanie na odpowied",
                                                  "witryna sprawdza", "cloudflare"])
            )

            if not is_challenge:
                resolved = True
                break

            # Human-like Turnstile click
            await _human_click_turnstile(page, wait_sec)
            await asyncio.sleep(1)

        if not resolved:
            logger.warning(f"[CF_SOLVER] [{label}] Not resolved: {url[:55]} after {wait_max}s")
            return None

        # Extra wait for page to fully render after challenge resolves
        # (some sites redirect after CF clearance, need time to load real content)
        await asyncio.sleep(2)

        # Wait for network to settle (lazy-loaded content)
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass  # Timeout is OK, we still got something

        html = await page.content()

        # If HTML is suspiciously short, wait more (redirect/lazy load)
        if html and 500 < len(html) < 10000:
            await asyncio.sleep(3)
            html = await page.content()
            if len(html) < 2000:
                logger.warning(f"[CF_SOLVER] [{label}] Too short: {url[:55]} ({len(html)} chars)")
                return None

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
        elif any(x in err_str for x in ["Target page", "browser has been closed",
                                          "context or browser", "Connection closed",
                                          "Browser closed", "not connected"]):
            # Browser died — signal for restart (don't count as normal fail)
            logger.warning(f"[CF_SOLVER] [{label}] Browser DEAD: {err_str[:60]} — triggering restart")
            raise _BrowserDeadError(err_str)
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


async def _ensure_camoufox():
    """Lazy-init Camoufox browser for HARD_SHOPS. Firefox-based anti-detect."""
    global _camoufox_browser

    if _camoufox_browser:
        # Check if browser is still connected (crash recovery)
        try:
            if hasattr(_camoufox_browser, 'is_connected') and not _camoufox_browser.is_connected():
                logger.warning("[CF_SOLVER] Camoufox browser disconnected — resetting for re-init")
                await _close_camoufox()
            else:
                return _camoufox_browser
        except Exception:
            logger.warning("[CF_SOLVER] Camoufox health check failed — resetting for re-init")
            await _close_camoufox()

    async with _lock:
        # Double-check after acquiring lock
        if _camoufox_browser:
            try:
                if hasattr(_camoufox_browser, 'is_connected') and not _camoufox_browser.is_connected():
                    await _close_camoufox()
                else:
                    return _camoufox_browser
            except Exception:
                await _close_camoufox()

        try:
            from camoufox.async_api import AsyncCamoufox
            logger.info("[CF_SOLVER] Starting Camoufox (Firefox anti-detect + proxy)...")

            # Camoufox context manager returns browser directly
            # We use it slightly differently — start and keep reference
            _cm = AsyncCamoufox(
                headless=True,  # Safe for Camoufox (Firefox fingerprint spoofed at C++ level)
                proxy={
                    "server": f"http://{PROXY_ADDR}",
                },
                geoip=True,  # Match geolocation to proxy IP
                humanize=True,  # Human-like cursor movement
                os="windows",  # Most common OS fingerprint
                disable_coop=True,  # Allow clicking Turnstile in cross-origin iframe
            )
            _camoufox_browser = await _cm.__aenter__()
            # Store context manager to close later
            _camoufox_browser._cm = _cm
            logger.info("[CF_SOLVER] Camoufox ready (Firefox + proxy + geoip)")
            return _camoufox_browser

        except ImportError as e:
            logger.error(f"[CF_SOLVER] Camoufox import failed: {e}")
            return None
        except Exception as e:
            logger.error(f"[CF_SOLVER] Camoufox start failed: {type(e).__name__}: {e}")
            _camoufox_browser = None
            return None


async def _close_camoufox():
    """Safely close Camoufox browser and reset global reference."""
    global _camoufox_browser
    if _camoufox_browser:
        try:
            if hasattr(_camoufox_browser, '_cm'):
                await _camoufox_browser._cm.__aexit__(None, None, None)
            else:
                await _camoufox_browser.close()
        except Exception:
            pass
    _camoufox_browser = None


async def _solve_with_camoufox(url, timeout):
    """Solve CF challenge using Camoufox (Firefox anti-detect). For HARD_SHOPS only."""
    browser = await _ensure_camoufox()
    if not browser:
        return None

    page = None
    try:
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)

        # Wait for CF challenge to resolve (same logic as Chromium path)
        shop = _get_shop_from_url(url)
        wait_max = CF_WAIT_MAX + 15  # HARD_SHOPS always get extended time

        resolved = False
        for wait_sec in range(wait_max):
            title = await page.title()
            content_check = await page.evaluate(
                "() => document.body ? document.body.innerText.substring(0, 200) : ''"
            )
            title_lower = (title or "").lower()
            content_lower = (content_check or "").lower()

            is_challenge = (
                any(x in title_lower for x in ["moment", "checking", "attention", "just a moment"]) or
                any(x in content_lower for x in ["verif", "checking your browser", "please wait",
                                                  "enable javascript", "ray id",
                                                  "weryfikac", "czekanie na odpowied",
                                                  "witryna sprawdza", "cloudflare"])
            )

            if not is_challenge:
                resolved = True
                break

            # Camoufox has humanize=True, just click in iframe area
            if wait_sec in TURNSTILE_CLICK_AT:
                try:
                    # Simple click approach — Camoufox handles humanization
                    await page.mouse.click(210, 290)
                    await asyncio.sleep(1)
                except Exception:
                    pass

            await asyncio.sleep(1)

        if not resolved:
            logger.warning(f"[CF_SOLVER] [camoufox] Not resolved: {url[:55]} after {wait_max}s")
            return None

        await asyncio.sleep(2)
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass

        html = await page.content()

        if not html or len(html) < 500:
            logger.warning(f"[CF_SOLVER] [camoufox] Empty: {url[:55]} ({len(html or '')} chars)")
            return None

        logger.info(f"[CF_SOLVER] [camoufox] Solved OK: {url[:50]} ({len(html)} chars)")
        return html

    except Exception as e:
        err_str = str(e)
        # Detect browser crash — reset for lazy re-init on next call
        if any(x in err_str for x in ["Target page", "browser has been closed",
                                        "context or browser", "Connection closed",
                                        "Browser closed", "not connected"]):
            logger.warning(f"[CF_SOLVER] [camoufox] Browser crashed: {err_str[:60]} — will re-init")
            await _close_camoufox()
        else:
            logger.error(f"[CF_SOLVER] [camoufox] Error: {url[:55]}: {err_str[:80]}")
        return None
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass


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

    # HARD_SHOPS: use separate Camoufox semaphore (doesn't block Chromium slots)
    if _get_shop_from_url(url) in HARD_SHOPS:
        async with _camoufox_semaphore:
            html = await _solve_with_camoufox(url, timeout)
            if html:
                _consecutive_fails = 0
                return html
            # Camoufox failed — don't count toward Chromium restart threshold
            # _solve_with_camoufox handles its own crash recovery (resets _camoufox_browser)
            return None

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

            try:
                html = await _solve_with_browser(browser, url, timeout, label)
            except _BrowserDeadError:
                # Browser process died — restart immediately and retry with other browser
                logger.warning(f"[CF_SOLVER] Browser '{label}' died during solve — restarting...")
                asyncio.ensure_future(_restart_browsers())
                continue

            if html:
                _consecutive_fails = 0
                return html

        # Both paths failed
        _consecutive_fails += 1
        if _consecutive_fails >= RESTART_THRESHOLD:
            await _restart_browsers()

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


async def health_check():
    """
    Proactive health check — verify browsers are alive and responsive.
    Call periodically (e.g. every 5 min) from the SLOW process.
    Returns True if healthy, False if restart was needed.
    """
    global _browser_proxy, _browser_direct, _camoufox_browser, _started, _consecutive_fails

    if not _started:
        return True  # Not started yet, will init on first use

    needs_restart = False

    if _browser_proxy and not _browser_proxy.is_connected():
        logger.warning("[CF_SOLVER] Health check: proxy browser disconnected!")
        needs_restart = True

    if _browser_direct and not _browser_direct.is_connected():
        logger.warning("[CF_SOLVER] Health check: direct browser disconnected!")
        needs_restart = True

    # Check Camoufox health separately (reset without full restart)
    if _camoufox_browser:
        try:
            if hasattr(_camoufox_browser, 'is_connected') and not _camoufox_browser.is_connected():
                logger.warning("[CF_SOLVER] Health check: Camoufox disconnected — resetting")
                await _close_camoufox()
        except Exception:
            logger.warning("[CF_SOLVER] Health check: Camoufox check failed — resetting")
            await _close_camoufox()

    # If consecutive fails are high but below restart threshold, preemptively restart
    if _consecutive_fails >= 10:
        logger.warning(f"[CF_SOLVER] Health check: {_consecutive_fails} consecutive fails — preemptive restart")
        needs_restart = True

    if needs_restart:
        await _restart_browsers()
        return False

    return True


async def close():
    """Shutdown all browsers."""
    global _browser_proxy, _browser_direct, _camoufox_browser, _pw, _started, _consecutive_fails
    _consecutive_fails = 0
    for b in [_browser_proxy, _browser_direct]:
        if b:
            try:
                await b.close()
            except Exception:
                pass
    # Close Camoufox via its context manager
    await _close_camoufox()
    _browser_proxy = None
    _browser_direct = None
    _camoufox_browser = None
    if _pw:
        try:
            await _pw.stop()
        except Exception:
            pass
    _pw = None
    _started = False
    logger.info("[CF_SOLVER] Closed")
