"""
CF Solver — lightweight FlareSolverr replacement.

Uses persistent patchright browser (stealth, anti-detection) to solve
Cloudflare challenges and return page HTML.

WHY (vs FlareSolverr):
- FS spawns unlimited Chrome internally, never cleans up → 440 PIDs, 189% CPU
- This: 1 persistent browser, POOL of contexts, fresh page per request
- Context pool = no renderer churn (new_context/close per request spawned processes)
- Same API interface as FS: POST with url → get HTML back
- Runs in-process (no Docker, no separate service)

ARCHITECTURE:
- 1 browser process (shared)
- Pool of MAX_CONCURRENT persistent contexts (created at startup)
- solve() picks context from pool (round-robin), opens page, navigates, closes page
- Context lives forever (same renderer process reused)
- If context crashes → only that one is recreated
- Page is lightweight (no new renderer process)

USAGE (from shop scrapers — drop-in replacement):
    # Old (FlareSolverr):
    # payload = {"cmd": "request.get", "url": url, "maxTimeout": 30000}
    # async with session.post("http://localhost:8191/v1", json=payload) as resp: ...
    
    # New (CF Solver):
    from cf_solver import solve
    html = await solve(url, timeout=30)

RESOURCE USAGE:
- 1 browser + 2 persistent contexts (no churn)
- 1 page at a time per context (max 2 concurrent via semaphore)
- Page created → navigate → wait for CF → get HTML → page closed
- CPU: ~5% per active solve (vs FS 189% with accumulated garbage)
- RAM: ~50MB per active page (freed after solve)

SCALING:
- 10 shops × 2 min interval = 5 requests/min → semaphore(2) handles easily
- 50 shops × 2 min = 25 req/min → increase MAX_CONCURRENT to 4
- No accumulation regardless of scale (no context create/destroy per request)
"""
import asyncio
import logging
import os
import time

logger = logging.getLogger("monitor")

PROXY_ADDR = os.environ.get("PROXY_ADDR", "127.0.0.1:8888")
MAX_CONCURRENT = 4  # Max simultaneous CF solves (1 tab each, all closed after)
SOLVE_TIMEOUT = 50  # Max seconds to solve a challenge
CF_WAIT_MAX = 30    # Max seconds to wait for CF challenge resolution (was 20 — too short for Turnstile)
CONTEXT_MAX_AGE = 600  # Recycle contexts every 10 min (fresh cookies/fingerprint)

_browser = None
_pw = None
_semaphore = None
_lock = asyncio.Lock()
_started = False
_contexts = []
_context_idx = 0
_context_created_at = []  # Timestamps for context recycling
_consecutive_fails = 0    # Track global failures for auto-restart


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


async def _ensure_browser():
    """Start patchright browser if not running, create context pool."""
    global _browser, _pw, _semaphore, _started, _contexts, _context_created_at

    if _started and _browser and _browser.is_connected():
        return

    async with _lock:
        if _started and _browser and _browser.is_connected():
            return

        logger.info("[CF_SOLVER] Starting patchright browser...")
        from patchright.async_api import async_playwright
        _pw = await async_playwright().start()
        _browser = await _pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--disable-background-timer-throttling",
                f"--proxy-server=http://{PROXY_ADDR}",
            ]
        )
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        # Create persistent context pool (no per-request context churn)
        _contexts = []
        _context_created_at = []
        for i in range(MAX_CONCURRENT):
            ctx = await _browser.new_context(user_agent=UA)
            _contexts.append(ctx)
            _context_created_at.append(time.time())
            logger.info(f"[CF_SOLVER] Context pool[{i}] created")

        _started = True
        logger.info("[CF_SOLVER] Browser ready (patchright headless + proxy, pool=%d)", MAX_CONCURRENT)


async def _maybe_recycle_context(idx):
    """Recycle context if too old (stale cookies = CF remembers failed attempts)."""
    global _contexts, _context_created_at
    age = time.time() - _context_created_at[idx]
    if age > CONTEXT_MAX_AGE:
        try:
            await _contexts[idx].close()
        except Exception:
            pass
        _contexts[idx] = await _browser.new_context(user_agent=UA)
        _context_created_at[idx] = time.time()
        logger.info(f"[CF_SOLVER] Context[{idx}] recycled (age={int(age)}s)")


async def _restart_browser():
    """Full browser restart — nuclear option when all contexts are failing."""
    global _browser, _pw, _started, _contexts, _context_created_at, _consecutive_fails
    logger.warning("[CF_SOLVER] FULL RESTART — too many consecutive failures")
    # Close everything
    for ctx in _contexts:
        try:
            await ctx.close()
        except Exception:
            pass
    _contexts = []
    _context_created_at = []
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


async def solve(url, timeout=SOLVE_TIMEOUT, session_name=None):
    """
    Solve Cloudflare challenge and return page HTML.
    
    Enhanced with:
    - Turnstile iframe detection and waiting
    - Context recycling (stale cookies → CF refuses)
    - Auto browser restart after 20 consecutive failures
    - Extended wait time (30s vs old 20s)
    """
    await _ensure_browser()

    global _context_idx, _contexts, _consecutive_fails

    async with _semaphore:
        # Retry once on proxy failure (tunnel can have brief hiccups)
        for attempt in range(2):
            page = None
            idx = _context_idx
            _context_idx = (_context_idx + 1) % len(_contexts)

            # Recycle stale context (prevents cookie-based blocking)
            await _maybe_recycle_context(idx)
            context = _contexts[idx]

            try:
                page = await context.new_page()

                # Navigate
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)

                # Wait for CF challenge to resolve
                resolved = False
                for wait_sec in range(CF_WAIT_MAX):
                    title = await page.title()
                    content_check = await page.evaluate("() => document.body ? document.body.innerText.substring(0, 200) : ''")

                    # CF challenge indicators
                    title_lower = (title or "").lower()
                    content_lower = (content_check or "").lower()

                    is_challenge = (
                        any(x in title_lower for x in ["moment", "checking", "attention", "just a moment"]) or
                        any(x in content_lower for x in ["verif", "checking your browser", "please wait", "enable javascript"])
                    )

                    if not is_challenge:
                        resolved = True
                        break

                    # Try to find and click Turnstile checkbox (CF interactive challenge)
                    if wait_sec == 3 or wait_sec == 8 or wait_sec == 15:
                        try:
                            # Turnstile lives in an iframe
                            frames = page.frames
                            for frame in frames:
                                if "challenges.cloudflare.com" in (frame.url or ""):
                                    # Try clicking the checkbox
                                    checkbox = await frame.query_selector("input[type='checkbox'], .cb-i, #challenge-stage")
                                    if checkbox:
                                        await checkbox.click()
                                        logger.info(f"[CF_SOLVER] Clicked Turnstile checkbox for {url[:40]}")
                                        await asyncio.sleep(2)
                                        break
                        except Exception:
                            pass  # Not all challenges have clickable element

                    await asyncio.sleep(1)

                if not resolved:
                    logger.warning(f"[CF_SOLVER] Challenge not resolved for {url[:60]} after {CF_WAIT_MAX}s")
                    _consecutive_fails += 1
                    # Auto-restart after 20 consecutive failures (all contexts are poisoned)
                    if _consecutive_fails >= 20:
                        asyncio.ensure_future(_restart_browser())
                    return None

                # Get full HTML
                html = await page.content()

                if not html or len(html) < 500:
                    logger.warning(f"[CF_SOLVER] Empty response for {url[:60]}")
                    _consecutive_fails += 1
                    return None

                # Success! Reset failure counter
                _consecutive_fails = 0
                return html

            except asyncio.TimeoutError:
                logger.warning(f"[CF_SOLVER] Timeout {timeout}s for {url[:60]}")
                _consecutive_fails += 1
                return None
            except Exception as e:
                err_str = str(e)
                # Retry on proxy connection failure (brief tunnel hiccup)
                if "ERR_PROXY" in err_str or "Connect call failed" in err_str:
                    if attempt == 0:
                        logger.warning(f"[CF_SOLVER] Proxy fail for {url[:60]}, retry in 3s...")
                        if page:
                            try:
                                await page.close()
                            except Exception:
                                pass
                        await asyncio.sleep(3)
                        continue
                    else:
                        logger.error(f"[CF_SOLVER] Proxy fail AGAIN for {url[:60]}")
                        _consecutive_fails += 1
                        return None

                logger.error(f"[CF_SOLVER] Error for {url[:60]}: {err_str[:80]}")
                # If context crashed, recreate just this one
                if "closed" in err_str.lower() or "crash" in err_str.lower():
                    logger.warning(f"[CF_SOLVER] Context[{idx}] crashed, recreating...")
                    try:
                        _contexts[idx] = await _browser.new_context(user_agent=UA)
                        _context_created_at[idx] = time.time()
                        logger.info(f"[CF_SOLVER] Context[{idx}] recreated OK")
                    except Exception:
                        # Browser itself is dead, mark for full restart
                        global _started
                        _started = False
                _consecutive_fails += 1
                return None
            finally:
                # Close PAGE only — context stays alive (no renderer churn)
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass


async def solve_fs_compat(url, max_timeout=30000, session=None):
    """
    FlareSolverr-compatible interface.
    Returns dict like FS: {"status": "ok", "solution": {"response": html}}
    
    For easy migration: shops can switch from FS POST to this function
    with minimal code change.
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
    """Shutdown browser and context pool."""
    global _browser, _pw, _started, _contexts, _context_created_at, _consecutive_fails
    # Close all pooled contexts
    for ctx in _contexts:
        try:
            await ctx.close()
        except Exception:
            pass
    _contexts = []
    _context_created_at = []
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
