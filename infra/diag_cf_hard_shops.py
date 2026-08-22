#!/usr/bin/env python3
"""
FULL DIAGNOSTIC — CF HARD_SHOPS (xjoy, gralnia, battlestash)

Tests EVERYTHING in one run:
1. ~/.camoufox directory (known bug #572 — browser hangs if missing)
2. Camoufox import + binary existence
3. Proxy connectivity (all 3 paths)
4. Patchright Chromium direct (VPS IP) — can it solve CF on HARD_SHOPS?
5. Patchright Chromium + proxy — can it solve CF?
6. Camoufox + proxy — can it solve CF?
7. Camoufox direct (no proxy) — can it solve CF?
8. playwright-captcha availability (ClickSolver)
9. Full solve attempt on each HARD_SHOP URL

Run: DISPLAY=:99 ./venv/bin/python3 infra/diag_cf_hard_shops.py
"""
import asyncio
import os
import sys
import time
import subprocess
from pathlib import Path

HARD_SHOP_URLS = [
    ("xjoy", "https://www.xjoy.pl/278-pokemon-tcg"),
    ("gralnia", "https://gralnia.org/?s=pokemon+tcg&post_type=product"),
    ("battlestash", "https://battlestash.pl/kategoria/gry-karciane/pokemon-tcg/"),
]

PROXY_ADDR = "127.0.0.1:8888"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

results = []

def log(msg, status="INFO"):
    icon = {"OK": "✅", "FAIL": "❌", "WARN": "⚠️", "INFO": "ℹ️"}.get(status, "•")
    line = f"  {icon} {msg}"
    print(line)
    results.append(line)


def section(title):
    line = f"\n{'='*60}\n  {title}\n{'='*60}"
    print(line)
    results.append(line)


async def test_camoufox_dir():
    section("1. ~/.camoufox DIRECTORY (bug #572)")
    home = Path.home()
    camoufox_dir = home / ".camoufox"
    cache_dir = home / ".cache" / "camoufox"
    
    if camoufox_dir.exists():
        log(f"~/.camoufox EXISTS: {camoufox_dir}", "OK")
        log(f"  Contents: {list(camoufox_dir.iterdir())[:5]}")
    else:
        log(f"~/.camoufox MISSING! Creating it now...", "WARN")
        camoufox_dir.mkdir(parents=True, exist_ok=True)
        log(f"  Created: {camoufox_dir}", "OK")
    
    if cache_dir.exists():
        log(f"~/.cache/camoufox EXISTS: {cache_dir}", "OK")
        # Check binary
        binary = cache_dir / "camoufox-bin"
        if binary.exists():
            log(f"  camoufox-bin: {binary} ({binary.stat().st_size / 1024 / 1024:.0f}MB)", "OK")
        else:
            # Try alternate locations
            alt = list(cache_dir.glob("**/camoufox*"))
            log(f"  camoufox-bin NOT at expected path. Found: {alt[:5]}", "WARN")
    else:
        log(f"~/.cache/camoufox MISSING — camoufox not installed?", "FAIL")


async def test_camoufox_import():
    section("2. CAMOUFOX IMPORT + VERSION")
    try:
        from camoufox.async_api import AsyncCamoufox
        import camoufox
        version = getattr(camoufox, '__version__', 'unknown')
        log(f"camoufox imported OK, version: {version}", "OK")
    except ImportError as e:
        log(f"camoufox import FAILED: {e}", "FAIL")
        log("  Fix: ./venv/bin/pip install 'camoufox[geoip]'")


async def test_proxy():
    section("3. PROXY CONNECTIVITY")
    paths = [
        ("HTTP Tunnel", f"http://{PROXY_ADDR}"),
        ("Tailscale", "http://100.127.72.24:8888"),
        ("SOCKS5", "socks5://127.0.0.1:1080"),
    ]
    for name, proxy in paths:
        try:
            cmd = ["curl", "-x", proxy, "-s", "-o", "/dev/null", "-w", "%{http_code}",
                   "--connect-timeout", "10", "--max-time", "15", "https://www.google.com"]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            code = r.stdout.strip()
            if code in ("200", "301", "302"):
                log(f"{name} ({proxy}): {code}", "OK")
            else:
                log(f"{name} ({proxy}): HTTP {code}", "FAIL")
        except Exception as e:
            log(f"{name} ({proxy}): {type(e).__name__}: {e}", "FAIL")


async def test_patchright_direct(url, shop_name):
    """Test patchright Chromium WITHOUT proxy (VPS IP) on a HARD_SHOP URL."""
    try:
        from patchright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox",
                      "--disable-gpu", "--disable-dev-shm-usage"]
            )
            ctx = await browser.new_context(user_agent=UA, viewport={"width": 1920, "height": 1080})
            page = await ctx.new_page()
            
            t0 = time.time()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                pass  # timeout on goto is OK, page might still be usable
            
            # Wait for CF challenge
            resolved = False
            for i in range(45):
                title = await page.title()
                body = await page.evaluate("() => document.body ? document.body.innerText.substring(0, 200) : ''")
                if not any(x in (title + body).lower() for x in ["moment", "checking", "verif", "cloudflare", "weryfikac"]):
                    resolved = True
                    break
                # Try clicking Turnstile
                if i in [2, 5, 8, 12, 18, 25, 32]:
                    try:
                        await page.mouse.click(210, 290)
                    except:
                        pass
                await asyncio.sleep(1)
            
            elapsed = time.time() - t0
            if resolved:
                html = await page.content()
                log(f"[{shop_name}] Patchright DIRECT: SOLVED in {elapsed:.1f}s ({len(html)} chars)", "OK")
            else:
                log(f"[{shop_name}] Patchright DIRECT: NOT SOLVED after {elapsed:.1f}s", "FAIL")
            
            await browser.close()
            return resolved
    except Exception as e:
        log(f"[{shop_name}] Patchright DIRECT: {type(e).__name__}: {str(e)[:80]}", "FAIL")
        return False


async def test_patchright_proxy(url, shop_name):
    """Test patchright Chromium WITH proxy on a HARD_SHOP URL."""
    try:
        from patchright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox",
                      "--disable-gpu", "--disable-dev-shm-usage",
                      f"--proxy-server=http://{PROXY_ADDR}"]
            )
            ctx = await browser.new_context(user_agent=UA, viewport={"width": 1920, "height": 1080})
            page = await ctx.new_page()
            
            t0 = time.time()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                pass
            
            resolved = False
            for i in range(45):
                title = await page.title()
                body = await page.evaluate("() => document.body ? document.body.innerText.substring(0, 200) : ''")
                if not any(x in (title + body).lower() for x in ["moment", "checking", "verif", "cloudflare", "weryfikac"]):
                    resolved = True
                    break
                if i in [2, 5, 8, 12, 18, 25, 32]:
                    try:
                        await page.mouse.click(210, 290)
                    except:
                        pass
                await asyncio.sleep(1)
            
            elapsed = time.time() - t0
            if resolved:
                html = await page.content()
                log(f"[{shop_name}] Patchright PROXY: SOLVED in {elapsed:.1f}s ({len(html)} chars)", "OK")
            else:
                log(f"[{shop_name}] Patchright PROXY: NOT SOLVED after {elapsed:.1f}s", "FAIL")
            
            await browser.close()
            return resolved
    except Exception as e:
        log(f"[{shop_name}] Patchright PROXY: {type(e).__name__}: {str(e)[:80]}", "FAIL")
        return False


async def test_camoufox_solve(url, shop_name, use_proxy=True):
    """Test Camoufox on a HARD_SHOP URL."""
    label = "PROXY" if use_proxy else "DIRECT"
    try:
        from camoufox.async_api import AsyncCamoufox
        
        kwargs = {
            "headless": True,
            "geoip": True,
            "humanize": True,
            "os": "windows",
        }
        if use_proxy:
            kwargs["proxy"] = {"server": f"http://{PROXY_ADDR}"}
        
        async with AsyncCamoufox(**kwargs) as browser:
            page = await browser.new_page()
            
            t0 = time.time()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=120000)
            except Exception as e:
                elapsed = time.time() - t0
                log(f"[{shop_name}] Camoufox {label}: goto FAILED after {elapsed:.1f}s — {str(e)[:60]}", "FAIL")
                return False
            
            resolved = False
            for i in range(55):
                title = await page.title()
                body = await page.evaluate("() => document.body ? document.body.innerText.substring(0, 200) : ''")
                if not any(x in (title + body).lower() for x in ["moment", "checking", "verif", "cloudflare", "weryfikac"]):
                    resolved = True
                    break
                if i in [2, 5, 8, 12, 18, 25, 32, 40]:
                    try:
                        await page.mouse.click(210, 290)
                    except:
                        pass
                await asyncio.sleep(1)
            
            elapsed = time.time() - t0
            if resolved:
                html = await page.content()
                log(f"[{shop_name}] Camoufox {label}: SOLVED in {elapsed:.1f}s ({len(html)} chars)", "OK")
            else:
                log(f"[{shop_name}] Camoufox {label}: NOT SOLVED after {elapsed:.1f}s", "FAIL")
            
            return resolved
    except Exception as e:
        log(f"[{shop_name}] Camoufox {label}: {type(e).__name__}: {str(e)[:80]}", "FAIL")
        return False


async def test_playwright_captcha():
    section("8. playwright-captcha (ClickSolver)")
    try:
        from playwright_captcha import CaptchaType, ClickSolver, FrameworkType
        log("playwright-captcha imported OK", "OK")
        log(f"  CaptchaType: {[x.name for x in CaptchaType]}")
        log(f"  FrameworkType: {[x.name for x in FrameworkType]}")
        return True
    except ImportError as e:
        log(f"playwright-captcha NOT installed: {e}", "WARN")
        log("  Fix: ./venv/bin/pip install playwright-captcha")
        return False


async def test_playwright_captcha_solve(url, shop_name):
    """Test playwright-captcha ClickSolver on a HARD_SHOP URL with patchright."""
    try:
        from playwright_captcha import CaptchaType, ClickSolver, FrameworkType
        from patchright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox",
                      "--disable-gpu", "--disable-dev-shm-usage",
                      f"--proxy-server=http://{PROXY_ADDR}"]
            )
            ctx = await browser.new_context(user_agent=UA, viewport={"width": 1920, "height": 1080})
            page = await ctx.new_page()
            
            t0 = time.time()
            
            async with ClickSolver(framework=FrameworkType.PATCHRIGHT, page=page, max_attempts=3, attempt_delay=3) as solver:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                except Exception:
                    pass
                
                # Check if CF challenge present
                await asyncio.sleep(2)
                title = await page.title()
                body = await page.evaluate("() => document.body ? document.body.innerText.substring(0, 200) : ''")
                is_challenge = any(x in (title + body).lower() for x in ["moment", "checking", "verif", "cloudflare"])
                
                if is_challenge:
                    # Use ClickSolver
                    try:
                        await solver.solve_captcha(
                            captcha_container=page,
                            captcha_type=CaptchaType.CLOUDFLARE_TURNSTILE
                        )
                        await asyncio.sleep(3)
                    except Exception as e:
                        log(f"[{shop_name}] ClickSolver: solve_captcha error: {str(e)[:60]}", "WARN")
                
                # Check result
                await asyncio.sleep(2)
                title2 = await page.title()
                body2 = await page.evaluate("() => document.body ? document.body.innerText.substring(0, 200) : ''")
                still_challenge = any(x in (title2 + body2).lower() for x in ["moment", "checking", "verif", "cloudflare"])
                
                elapsed = time.time() - t0
                if not still_challenge:
                    html = await page.content()
                    log(f"[{shop_name}] ClickSolver PROXY: SOLVED in {elapsed:.1f}s ({len(html)} chars)", "OK")
                else:
                    log(f"[{shop_name}] ClickSolver PROXY: NOT SOLVED after {elapsed:.1f}s", "FAIL")
            
            await browser.close()
    except ImportError:
        log(f"[{shop_name}] ClickSolver: playwright-captcha not installed — skipping", "WARN")
    except Exception as e:
        log(f"[{shop_name}] ClickSolver PROXY: {type(e).__name__}: {str(e)[:80]}", "FAIL")


async def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  DIAGNOSTIC: CF HARD_SHOPS (xjoy/gralnia/battlestash)      ║")
    print(f"║  {time.strftime('%Y-%m-%d %H:%M:%S')}                                      ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    
    # Step 1-3: Environment checks
    await test_camoufox_dir()
    await test_camoufox_import()
    await test_proxy()
    
    # Step 4-5: Test each method on xjoy (hardest shop)
    test_url = HARD_SHOP_URLS[0]  # xjoy
    
    section(f"4. PATCHRIGHT DIRECT (VPS IP) — {test_url[0]}")
    await test_patchright_direct(test_url[1], test_url[0])
    
    section(f"5. PATCHRIGHT PROXY (mobile IP) — {test_url[0]}")
    await test_patchright_proxy(test_url[1], test_url[0])
    
    section(f"6. CAMOUFOX + PROXY — {test_url[0]}")
    await test_camoufox_solve(test_url[1], test_url[0], use_proxy=True)
    
    section(f"7. CAMOUFOX DIRECT (no proxy) — {test_url[0]}")
    await test_camoufox_solve(test_url[1], test_url[0], use_proxy=False)
    
    # Step 8: playwright-captcha
    has_pc = await test_playwright_captcha()
    
    # Step 9: ClickSolver test (if available)
    if has_pc:
        section(f"9. CLICK_SOLVER + PATCHRIGHT PROXY — {test_url[0]}")
        await test_playwright_captcha_solve(test_url[1], test_url[0])
    
    # Summary
    section("SUMMARY")
    ok_count = sum(1 for r in results if "✅" in r)
    fail_count = sum(1 for r in results if "❌" in r)
    warn_count = sum(1 for r in results if "⚠️" in r)
    log(f"Results: {ok_count} OK, {fail_count} FAIL, {warn_count} WARN")
    log(f"Total time: {time.time() - start_time:.0f}s")
    
    print("\n" + "="*60)
    print("  DONE — paste the output URL back to chat")
    print("="*60)


if __name__ == "__main__":
    start_time = time.time()
    asyncio.run(main())
