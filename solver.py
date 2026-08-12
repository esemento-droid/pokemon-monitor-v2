"""
Universal Challenge Solver — auto-detects and handles ALL obstacles.

Usage:
    from solver import SmartSolver

    solver = SmartSolver(page, 'shopname', webhook_url='...')
    solved = await solver.handle_challenge()  # True = page clear, False = still blocked

Handles:
    - Cloudflare managed challenge → FlareSolverr
    - Cloudflare JS challenge → wait (Patchright handles)
    - reCAPTCHA v2/v3 → Capsolver API
    - hCaptcha → Capsolver API
    - Rate limit (429) → exponential backoff
    - IP ban (403 + "blocked") → trigger IP rotation
    - WAF block → retry with delay
    - Age gate → auto-click confirm
    - Cookie consent → auto-dismiss
    - Verification screen → wait + Discord notify
"""
import asyncio
import logging
import time
import os
from typing import Optional
from pathlib import Path

log = logging.getLogger("solver")

BASE_DIR = Path("/opt/pokemon-monitor-v2")
CAPSOLVER_KEY = os.environ.get("CAPSOLVER_KEY", "")
FLARESOLVERR_URL = "http://localhost:8191/v1"


class SmartSolver:
    """Attach to a Playwright page. Call handle_challenge() when blocked."""

    def __init__(self, page, shop_name: str = "", webhook_url: str = ""):
        self.page = page
        self.shop = shop_name
        self.webhook_url = webhook_url
        self.retry_count = 0
        self.max_retries = 3

    async def detect_challenge(self) -> Optional[str]:
        """Detect what type of challenge/block is present. Returns type or None."""
        try:
            content = await self.page.content()
            title = await self.page.title()

            # Cloudflare
            if "challenge-platform" in content or "cf-browser-verification" in content:
                return "cloudflare_managed"
            if title == "Just a moment...":
                return "cloudflare_js"
            if "ray ID" in content.lower() and "cloudflare" in content.lower():
                return "cloudflare_block"

            # CAPTCHA
            if "g-recaptcha" in content or "recaptcha/api" in content:
                return "recaptcha"
            if "h-captcha" in content or "hcaptcha.com" in content:
                return "hcaptcha"

            # Rate limit
            if "429" in title or "too many requests" in content.lower():
                return "rate_limit"

            # IP ban / WAF
            if "403" in title or "access denied" in content.lower():
                if any(kw in content.lower() for kw in ["ip", "adres", "zablokowany", "banned"]):
                    return "ip_ban"
                return "waf_block"

            # Age gate
            if any(kw in content.lower() for kw in [
                "czy masz 18", "potwierdź wiek", "age verification", "18+"
            ]):
                return "age_gate"

            # Cookie consent (blocking overlay)
            if any(kw in content.lower() for kw in ["cookie", "ciasteczk"]):
                overlays = await self.page.locator(
                    "[class*='cookie'], [class*='consent'], #cookie, #consent, #cc--main"
                ).count()
                if overlays > 0:
                    return "cookie_consent"

            # Verification
            if any(kw in content.lower() for kw in [
                "weryfikacja", "verification", "sprawdzanie", "checking"
            ]):
                return "verification"

            return None
        except Exception as e:
            log.error(f"Challenge detection error: {e}")
            return None

    async def handle_challenge(self) -> bool:
        """Auto-detect and solve. Returns True if resolved."""
        challenge = await self.detect_challenge()
        if not challenge:
            return True

        log.info(f"[{self.shop}] Challenge detected: {challenge}")

        handlers = {
            "cloudflare_managed": self._solve_cf_managed,
            "cloudflare_js": self._solve_cf_js,
            "cloudflare_block": self._handle_ip_ban,
            "recaptcha": self._solve_captcha,
            "hcaptcha": self._solve_captcha,
            "rate_limit": self._handle_rate_limit,
            "ip_ban": self._handle_ip_ban,
            "waf_block": self._handle_waf_block,
            "age_gate": self._solve_age_gate,
            "cookie_consent": self._solve_cookie_consent,
            "verification": self._handle_verification,
        }

        handler = handlers.get(challenge, self._handle_unknown)
        try:
            result = await handler()
            if result:
                log.info(f"[{self.shop}] Challenge {challenge} SOLVED")
            else:
                log.warning(f"[{self.shop}] Challenge {challenge} FAILED")
            return result
        except Exception as e:
            log.error(f"[{self.shop}] Solver error: {e}")
            return False

    # === HANDLERS ===

    async def _solve_cf_managed(self) -> bool:
        """Cloudflare managed challenge — use FlareSolverr."""
        try:
            import aiohttp
            url = self.page.url
            async with aiohttp.ClientSession() as session:
                resp = await session.post(FLARESOLVERR_URL, json={
                    "cmd": "request.get",
                    "url": url,
                    "maxTimeout": 60000,
                })
                data = await resp.json()
                if data.get("status") == "ok":
                    cookies = data.get("solution", {}).get("cookies", [])
                    for c in cookies:
                        await self.page.context.add_cookies([{
                            "name": c["name"],
                            "value": c["value"],
                            "domain": c.get("domain", ""),
                            "path": c.get("path", "/"),
                        }])
                    await self.page.reload()
                    await self.page.wait_for_timeout(3000)
                    return await self.detect_challenge() is None
        except Exception as e:
            log.error(f"FlareSolverr failed: {e}")
        return False

    async def _solve_cf_js(self) -> bool:
        """CF JS challenge — Patchright handles automatically, just wait."""
        log.info(f"[{self.shop}] Waiting for CF JS challenge auto-solve...")
        for _ in range(20):
            await self.page.wait_for_timeout(2000)
            if await self.detect_challenge() is None:
                return True
        return False

    async def _solve_captcha(self) -> bool:
        """reCAPTCHA / hCaptcha — use Capsolver API."""
        if not CAPSOLVER_KEY:
            await self._notify(f"⚠️ CAPTCHA na {self.shop} — brak CAPSOLVER_KEY!")
            return False
        try:
            import aiohttp
            sitekey = await self.page.evaluate("""() => {
                const el = document.querySelector('[data-sitekey]');
                return el ? el.getAttribute('data-sitekey') : null;
            }""")
            if not sitekey:
                log.error("No sitekey found on page")
                return False

            challenge_type = await self.detect_challenge()
            task_type = "HCaptchaTaskProxyLess" if challenge_type == "hcaptcha" else "ReCaptchaV2TaskProxyLess"

            async with aiohttp.ClientSession() as session:
                # Create task
                resp = await session.post("https://api.capsolver.com/createTask", json={
                    "clientKey": CAPSOLVER_KEY,
                    "task": {
                        "type": task_type,
                        "websiteURL": self.page.url,
                        "websiteKey": sitekey,
                    }
                })
                task_data = await resp.json()
                task_id = task_data.get("taskId")
                if not task_id:
                    log.error(f"Capsolver createTask failed: {task_data}")
                    return False

                # Poll for result (max 120s)
                for _ in range(60):
                    await asyncio.sleep(3)
                    resp = await session.post("https://api.capsolver.com/getTaskResult", json={
                        "clientKey": CAPSOLVER_KEY,
                        "taskId": task_id,
                    })
                    result = await resp.json()
                    if result.get("status") == "ready":
                        token = result["solution"]["gRecaptchaResponse"]
                        # Inject token
                        await self.page.evaluate("""(token) => {
                            const el = document.getElementById('g-recaptcha-response')
                                || document.querySelector('[name="h-captcha-response"]')
                                || document.querySelector('[name="g-recaptcha-response"]');
                            if (el) el.value = token;
                        }""", token)
                        log.info(f"[{self.shop}] CAPTCHA solved via Capsolver")
                        return True
                log.error("Capsolver timeout (120s)")
                return False
        except Exception as e:
            log.error(f"Capsolver failed: {e}")
            return False

    async def _handle_rate_limit(self) -> bool:
        """429 — exponential backoff."""
        self.retry_count += 1
        if self.retry_count > self.max_retries:
            log.error(f"[{self.shop}] Rate limit — max retries exceeded")
            return False
        wait = min(2 ** self.retry_count * 5, 60)
        log.info(f"[{self.shop}] Rate limited — wait {wait}s (retry {self.retry_count}/{self.max_retries})")
        await asyncio.sleep(wait)
        await self.page.reload()
        await self.page.wait_for_timeout(3000)
        return await self.detect_challenge() is None

    async def _handle_ip_ban(self) -> bool:
        """IP banned — trigger rotation and wait."""
        log.warning(f"[{self.shop}] IP BANNED — triggering rotation")
        try:
            from proxy_router import request_ip_rotation, invalidate_proxy
            for n in ["mobile_tunnel", "mobile_tailscale", "mobile_socks"]:
                invalidate_proxy(n)
            request_ip_rotation()
        except ImportError:
            log.error("proxy_router not available")
        await self._notify(f"⚠️ IP BANNED na {self.shop}! Rotacja uruchomiona, czekam 90s...")
        await asyncio.sleep(90)
        await self.page.reload()
        await self.page.wait_for_timeout(5000)
        return await self.detect_challenge() is None

    async def _handle_waf_block(self) -> bool:
        """WAF block — wait and retry."""
        log.warning(f"[{self.shop}] WAF block — retry in 10s")
        await asyncio.sleep(10)
        await self.page.reload()
        await self.page.wait_for_timeout(5000)
        return await self.detect_challenge() is None

    async def _solve_age_gate(self) -> bool:
        """Age gate — auto-click confirm."""
        selectors = [
            "button:has-text('Tak')", "button:has-text('Potwierdź')",
            "button:has-text('Yes')", "button:has-text('Confirm')",
            "a:has-text('Tak')", "a:has-text('Mam 18')",
            ".skyshop-alert-conditional-access button",
            ".age-gate button", "[data-age-confirm]",
        ]
        for sel in selectors:
            try:
                el = self.page.locator(sel).first
                if await el.is_visible(timeout=1000):
                    await el.click(force=True)
                    await self.page.wait_for_timeout(1000)
                    return True
            except Exception:
                continue
        return False

    async def _solve_cookie_consent(self) -> bool:
        """Cookie consent — accept/dismiss."""
        selectors = [
            "#c-p-bn", "button:has-text('Akceptuję')", "button:has-text('Zgadzam')",
            "button:has-text('Accept')", "button:has-text('OK')",
            "button:has-text('Rozumiem')", "button:has-text('Zamknij')",
            "[data-action='accept']", ".cookie-accept",
        ]
        for sel in selectors:
            try:
                el = self.page.locator(sel).first
                if await el.is_visible(timeout=1000):
                    await el.click(force=True)
                    await self.page.wait_for_timeout(500)
                    return True
            except Exception:
                continue
        # Fallback: remove overlay via JS
        await self.page.evaluate("""() => {
            document.querySelectorAll('[class*="cookie"], [class*="consent"], [class*="gdpr"], #cc--main, #cm')
                .forEach(el => el.remove());
        }""")
        return True

    async def _handle_verification(self) -> bool:
        """Verification screen — wait + notify human."""
        await self._notify(f"🔐 WERYFIKACJA na {self.shop}! Sprawdź email/SMS.")
        from bot_utils import wait_for_verification
        return await wait_for_verification(self.page, max_wait=300)

    async def _handle_unknown(self) -> bool:
        """Unknown block — screenshot + alert."""
        try:
            ss_path = f"/tmp/solver_{self.shop}_{int(time.time())}.png"
            await self.page.screenshot(path=ss_path)
            log.error(f"[{self.shop}] Unknown challenge — screenshot: {ss_path}")
        except Exception:
            pass
        await self._notify(f"❓ Nieznana blokada na {self.shop}! Ręczna interwencja.")
        return False

    async def _notify(self, msg: str):
        """Send Discord alert."""
        try:
            if not self.webhook_url:
                wh = BASE_DIR / "discord_webhook_jc.txt"
                if wh.exists():
                    self.webhook_url = wh.read_text().strip()
            if self.webhook_url:
                import aiohttp
                async with aiohttp.ClientSession() as s:
                    await s.post(self.webhook_url, json={"content": msg})
        except Exception:
            pass
