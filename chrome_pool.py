"""
Chrome Pool — persistent browser pool for NODRIVER process.

Replaces: 12 shops each launching/killing Chrome = 35 procs = load 18
Now: N persistent browsers, shops rotate through them via scheduler.

Architecture:
- PlaywrightPool: persistent headless browsers (for playwright shops)
- Nodriver/Patchright: controlled via semaphore (they need own browser binary)
- Scheduler: round-robin assigns shops to free browser slots
- Timeout: shop scan >90s = context killed, browser lives, slot freed
- No shop blocks another — timeout guarantees slot release

Pool sizing:
- Default: CHROME_POOL_SIZE env var (or auto-calculated)
- Auto: min(num_shops // 2, cpu_cores * 2, 8)
- 4 cores, 12 shops → 6 browsers (each shop every ~1 min)
- 4 cores, 50 shops → 8 browsers (each shop every ~3 min)
- 4 cores, 100 shops → 8 browsers (each shop every ~6 min)
- Scale vertically: more cores/RAM → increase CHROME_POOL_SIZE

For comparison (old system):
- 12 shops × own Chrome = 35 processes = load 18 CONSTANT
- New: 6 browsers = 18 processes = load ~4-5 CONSTANT
"""
import asyncio
import logging
import os
import multiprocessing

logger = logging.getLogger("monitor")


def _calc_pool_size(num_shops):
    """Calculate optimal pool size based on shops and hardware."""
    explicit = os.environ.get("CHROME_POOL_SIZE")
    if explicit:
        return int(explicit)
    cores = multiprocessing.cpu_count()
    # Max 2 browsers per core (headless is light), cap at 8 for 8GB RAM
    optimal = min(num_shops // 2, cores * 2, 8)
    return max(3, optimal)  # Minimum 3


class PlaywrightPool:
    """
    Pool of persistent Playwright headless browsers.
    Shops get a fresh context+page, do their scan, release.
    Browser stays alive between scans (zero startup cost).
    """

    def __init__(self, size):
        self.size = size
        self._browsers = []
        self._queue = None       # Queue of available browser indices
        self._pw = None
        self._started = False
        self._scan_timeout = 90  # Max seconds per shop scan

    async def start(self):
        """Initialize pool — launch N browsers."""
        if self._started:
            return

        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self._queue = asyncio.Queue()

        for i in range(self.size):
            browser = await self._launch(i)
            self._browsers.append(browser)
            await self._queue.put(i)

        self._started = True
        logger.info(f"[POOL] Playwright pool started: {self.size} browsers")

    async def _launch(self, idx):
        """Launch one headless browser."""
        try:
            browser = await self._pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-setuid-sandbox",
                    "--disable-background-timer-throttling",
                    "--disable-breakpad",
                ]
            )
            return browser
        except Exception as e:
            logger.error(f"[POOL] Browser #{idx} launch failed: {e}")
            return None

    async def _respawn(self, idx):
        """Kill and relaunch a browser."""
        old = self._browsers[idx]
        if old:
            try:
                await old.close()
            except Exception:
                pass
        browser = await self._launch(idx)
        self._browsers[idx] = browser
        return browser

    async def run_shop(self, shop_name, scan_fn):
        """
        Execute a shop's scan function with a pooled browser page.
        
        scan_fn can be:
        - New style: async def scan_fn(page) -> list  (gets page from pool)
        - Legacy: async def scan_fn() -> list  (launches own browser, pool just limits concurrency)
        
        Guarantees:
        - Slot is ALWAYS released (even on crash/timeout)
        - Browser survives shop crashes
        - No shop can block others longer than scan_timeout
        """
        import inspect

        # Check if scan_fn accepts a 'page' argument (new style)
        sig = inspect.signature(scan_fn)
        uses_pool_page = len(sig.parameters) > 0

        if uses_pool_page:
            # NEW STYLE: give shop a page from pool browser
            idx = await self._queue.get()
            context = None
            try:
                browser = self._browsers[idx]
                if browser is None or not browser.is_connected():
                    logger.warning(f"[POOL] Browser #{idx} dead, respawning for [{shop_name}]")
                    browser = await self._respawn(idx)
                    if browser is None:
                        return []

                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                )
                page = await context.new_page()

                products = await asyncio.wait_for(scan_fn(page), timeout=self._scan_timeout)
                return products if products else []

            except asyncio.TimeoutError:
                logger.warning(f"[POOL] [{shop_name}] TIMEOUT {self._scan_timeout}s")
                return []
            except Exception as e:
                logger.error(f"[POOL] [{shop_name}] ERROR: {e}")
                return []
            finally:
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass
                await self._queue.put(idx)
        else:
            # LEGACY: shop launches own browser, pool just controls concurrency
            idx = await self._queue.get()
            try:
                products = await asyncio.wait_for(scan_fn(), timeout=self._scan_timeout)
                return products if products else []
            except asyncio.TimeoutError:
                logger.warning(f"[POOL] [{shop_name}] TIMEOUT {self._scan_timeout}s (legacy)")
                return []
            except Exception as e:
                logger.error(f"[POOL] [{shop_name}] ERROR: {e}")
                return []
            finally:
                await self._queue.put(idx)

    async def close(self):
        """Shutdown all browsers."""
        for browser in self._browsers:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
        if self._pw:
            await self._pw.stop()
        self._started = False
        logger.info("[POOL] Playwright pool closed")


class SubprocessPool:
    """
    Semaphore-based pool for nodriver/patchright shops.
    These shops MUST launch their own browser (different binary/flags).
    Pool just limits how many run simultaneously.
    """

    def __init__(self, max_concurrent, name="SUBPROCESS"):
        self.max_concurrent = max_concurrent
        self.name = name
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def run_shop(self, shop_name, run_fn, timeout=120):
        """
        Run shop function with concurrency limit + timeout.
        run_fn: async function that launches its own browser and returns products.
        Guarantees: slot released even on timeout/crash. Kills orphan Chrome.
        """
        async with self._semaphore:
            try:
                result = await asyncio.wait_for(run_fn(), timeout=timeout)
                return result if result else []
            except asyncio.TimeoutError:
                logger.warning(f"[{self.name}] [{shop_name}] TIMEOUT {timeout}s — killing orphans")
                # Kill any runner.py for this shop + its Chrome children
                import subprocess as sp
                try:
                    sp.run(["pkill", "-9", "-f", f"runner.py {shop_name}"], capture_output=True, timeout=5)
                except Exception:
                    pass
                return []
            except Exception as e:
                logger.error(f"[{self.name}] [{shop_name}] ERROR: {e}")
                return []
