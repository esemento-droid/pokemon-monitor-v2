#!/usr/bin/env python3
"""Debug: check browser fingerprint and what Sellingo sees"""
import asyncio
from patchright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--proxy-server=http://127.0.0.1:8888']
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pl-PL"
        )
        page = await ctx.new_page()

        # Fix fingerprint: override platform and webgl
        await page.add_init_script("""
            Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
            Object.defineProperty(navigator, 'languages', {get: () => ['pl-PL', 'pl', 'en-US', 'en']});
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(param) {
                if (param === 37445) return 'Intel Inc.';
                if (param === 37446) return 'Intel Iris OpenGL Engine';
                return getParameter.call(this, param);
            };
        """)

        # Check fingerprint BEFORE anything else
        await page.goto('https://tcgumisia.pl', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(5)

        fp = await page.evaluate("""() => {
            return {
                webdriver: navigator.webdriver,
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                languages: navigator.languages,
                hardwareConcurrency: navigator.hardwareConcurrency,
                deviceMemory: navigator.deviceMemory,
                plugins: navigator.plugins.length,
                webgl: !!document.createElement('canvas').getContext('webgl'),
                chrome: !!window.chrome,
                permissions: typeof navigator.permissions,
                cookieEnabled: navigator.cookieEnabled,
                doNotTrack: navigator.doNotTrack,
                viewport: `${window.innerWidth}x${window.innerHeight}`,
                screenRes: `${screen.width}x${screen.height}`,
                colorDepth: screen.colorDepth,
                touchPoints: navigator.maxTouchPoints
            };
        }""")
        print("=== FINGERPRINT ===")
        for k, v in fp.items():
            flag = " <<<< DETECTED!" if k == 'webdriver' and v else ""
            print(f"  {k}: {v}{flag}")

        # Now login and add to cart, check the actual request/response
        print("\n=== LOGIN ===")
        try:
            await page.locator('.js-accept-cookie-alert-1').click(timeout=3000)
            await asyncio.sleep(1)
        except:
            pass
        await page.locator('button[data-aside-target="modal-aside-entry-form"]').click()
        await asyncio.sleep(2)
        email_input = page.locator('.js-login-form input[type="email"], .js-login-form input[placeholder*="E-mail"]').first
        pass_input = page.locator('.js-login-form input[type="password"]').first
        await email_input.click()
        await email_input.fill('t11008543@gmail.com')
        await asyncio.sleep(0.5)
        await pass_input.click()
        await pass_input.fill('mt!cSsphud4Zhnz')
        await asyncio.sleep(0.5)
        await page.locator('.js-submit-login').click()
        await asyncio.sleep(6)
        print("Login done")

        # Go to product and capture ATC request/response
        print("\n=== ATC ===")
        responses_log = []
        async def on_response(resp):
            url = resp.url.lower()
            if 'cart' in url or 'koszyk' in url or 'basket' in url or 'product' in url:
                try:
                    body = await resp.text()
                    responses_log.append(f"{resp.status} {resp.url} -> {body[:200]}")
                except:
                    responses_log.append(f"{resp.status} {resp.url} (no body)")
        page.on('response', lambda r: asyncio.ensure_future(on_response(r)))

        await page.goto('https://tcgumisia.pl/pokemon-tcg-ionos-bellibolt-ex-premium-collection', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(5)
        await page.locator('#product-card-add-to-card').click(timeout=5000)
        await asyncio.sleep(5)

        print(f"Captured {len(responses_log)} responses:")
        for r in responses_log:
            print(f"  {r}")

        # Check cart value
        cart = await page.evaluate("""() => {
            const el = document.querySelector('.js-cart-value');
            return el ? el.innerText : '?';
        }""")
        print(f"\nCart header value: {cart}")

        # Go to actual cart page and check price
        await page.goto('https://tcgumisia.pl/koszyk', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(4)
        cart_text = await page.evaluate("() => document.body.innerText.substring(0, 400)")
        print(f"\nCart page:\n{cart_text[:300]}")

        await ctx.close()
        await browser.close()

asyncio.run(main())
