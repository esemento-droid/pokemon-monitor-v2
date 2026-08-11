"""
Shared utilities for all autobuy bots.
Import: from bot_utils import wait_for_verification
"""
import asyncio
import logging

log = logging.getLogger("bot_utils")

VERIFICATION_KEYWORDS = [
    "weryfikacja", "weryfikuj", "sprawdzanie", "sprawdzamy",
    "verification", "verifying", "checking", "just a moment",
    "please wait", "proszę czekać", "prosze czekac",
    "confirm you are human", "potwierdź", "robot",
]


async def wait_for_verification(page, max_wait=15, check_interval=1.5):
    """
    Detect and wait for browser verification screens (JS challenges).
    Works with: Sellingo verification, CF JS challenge, custom bot checks.
    Call this after every page.goto() or navigation action.
    
    Returns True if page is clear, False if still blocked after max_wait.
    """
    for i in range(int(max_wait / check_interval)):
        try:
            # Check page title and body text for verification keywords
            title = await page.title()
            body_text = await page.evaluate(
                "() => document.body ? document.body.innerText.substring(0, 300).toLowerCase() : ''"
            )
            combined = (title.lower() + " " + body_text)

            # Check if any verification keyword is present
            is_verifying = any(kw in combined for kw in VERIFICATION_KEYWORDS)

            if not is_verifying:
                return True

            if i == 0:
                log.info(f"[VERIFY] Verification detected, waiting... (title='{title[:30]}')")

            await asyncio.sleep(check_interval)

        except Exception:
            await asyncio.sleep(check_interval)

    log.warning(f"[VERIFY] Still blocked after {max_wait}s")
    return False


async def safe_goto(page, url, wait_until="domcontentloaded", timeout=30000):
    """
    Navigate to URL and automatically wait for any verification to pass.
    Drop-in replacement for page.goto() in bots.
    """
    await page.goto(url, wait_until=wait_until, timeout=timeout)
    await asyncio.sleep(1)
    await wait_for_verification(page)
