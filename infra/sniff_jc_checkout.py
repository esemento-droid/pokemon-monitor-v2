#!/usr/bin/env python3
"""
Sniff JapanCollectibles checkout — capture all network requests during full buy flow.
Uses Playwright CDP (Chrome DevTools Protocol) to record every request/response.
Output: /tmp/jc_sniff_result.json with all requests made during checkout.
"""
import asyncio
import json
import time
from pathlib import Path
from patchright.async_api import async_playwright

SHOP_URL = "https://japancollectibles.shop"
PRODUCT_ID = "7437"  # Mega Heroes Mini Tin (70 PLN, qty=17)
ACCOUNT = {"email": "t11008543@gmail.com", "password": "mt!cSsphud4Zhnz"}
PROXY = {"server": "http://127.0.0.1:8888"}
OUTPUT = Path("/tmp/jc_sniff_result.json")

requests_log = []


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            proxy=PROXY,
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        # === CAPTURE ALL NETWORK ===
        async def on_request(request):
            entry = {
                "ts": time.time(),
                "method": request.method,
                "url": request.url,
                "headers": dict(request.headers),
                "post_data": request.post_data,
            }
            requests_log.append(entry)

        async def on_response(response):
            url = response.url
            # Only capture relevant responses (not images/css/js)
            if any(kw in url for kw in ['/cart', '/order', '/login', '/api', 'ajax', 'payment', 'delivery', 'shipment']):
                try:
                    body = await response.text()
                except:
                    body = ""
                # Find matching request
                for entry in reversed(requests_log):
                    if entry["url"] == url and "response" not in entry:
                        entry["response"] = {
                            "status": response.status,
                            "headers": dict(response.headers),
                            "body": body[:5000],  # Limit size
                        }
                        break

        page.on("request", on_request)
        page.on("response", on_response)

        print("=== STEP 1: Login ===")
        await page.goto(f"{SHOP_URL}/login", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)

        # Dismiss overlays
        await page.evaluate("""() => {
            document.getElementById('cc--main')?.remove();
            const ageBtn = document.querySelector('.skyshop-alert-conditional-access button');
            if (ageBtn) ageBtn.click();
        }""")
        await page.wait_for_timeout(1000)

        await page.fill("input#email", ACCOUNT["email"], timeout=5000)
        await page.fill("input[name='password']", ACCOUNT["password"], timeout=5000)
        await page.click("button[name='submit']", force=True)
        await page.wait_for_timeout(4000)
        print(f"Login done. URL: {page.url}")

        print("=== STEP 2: ATC ===")
        await page.goto(f"{SHOP_URL}/-p{PRODUCT_ID}", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)
        await page.evaluate("""() => {
            document.getElementById('cc--main')?.remove();
            document.querySelector('.fixed-elements')?.remove();
            document.querySelector('.skyshop-alert-conditional-access')?.remove();
        }""")

        try:
            atc = page.locator("button:has-text('Do koszyka'), button:has-text('Dodaj do koszyka')").first
            await atc.wait_for(state="visible", timeout=8000)
            await atc.click(force=True)
            print("ATC clicked")
        except Exception as e:
            print(f"ATC FAILED: {e}")
            await browser.close()
            return

        await page.wait_for_timeout(3000)

        print("=== STEP 3: Go to cart ===")
        await page.goto(f"{SHOP_URL}/cart/", wait_until="domcontentloaded", timeout=10000)
        await page.wait_for_timeout(5000)

        # Wait for cart hydration
        for _ in range(20):
            ready = await page.evaluate("""() => {
                const btn = document.querySelector('button[data-ng-click="order()"]');
                return btn && !btn.disabled;
            }""")
            if ready:
                break
            await page.wait_for_timeout(500)

        print("=== STEP 4: Click checkout ===")
        try:
            order_btn = page.locator('button[data-ng-click="order()"]:not([disabled])').first
            await order_btn.click()
        except:
            await page.evaluate("""() => {
                const btn = document.querySelector('button[data-ng-click="order()"]');
                if (btn) btn.click();
            }""")
        await page.wait_for_timeout(5000)

        print(f"After checkout click, URL: {page.url}")

        # Wait for payment options
        for _ in range(20):
            has_pay = await page.evaluate("() => document.body.innerText.includes('BLIK') || document.body.innerText.includes('Przelew')")
            if has_pay:
                break
            await page.wait_for_timeout(500)

        print("=== STEP 5: Select payment (BLIK) ===")
        try:
            blik = page.locator("text=BLIK").first
            await blik.click(force=True, timeout=5000)
            print("BLIK clicked")
        except Exception as e:
            print(f"BLIK click failed: {e}")
            # Try JS
            await page.evaluate("""() => {
                const els = document.querySelectorAll('*');
                for (const el of els) {
                    if (el.textContent.trim() === 'BLIK' || el.textContent.includes('BLIK')) {
                        el.click(); break;
                    }
                }
            }""")
        await page.wait_for_timeout(3000)

        print("=== STEP 6: Select delivery ===")
        try:
            kurier = page.locator("text=Kurier Inpost").first
            await kurier.click(force=True, timeout=5000)
            print("Kurier clicked")
        except Exception as e:
            print(f"Kurier click failed: {e}, trying Gabaryt")
            try:
                gab = page.locator("text=Gabaryt").first
                await gab.click(force=True, timeout=3000)
            except:
                pass
        await page.wait_for_timeout(2000)

        print("=== STEP 7: Checkboxes ===")
        checked = await page.evaluate("""() => {
            let c = 0;
            document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                if (!cb.checked) { cb.click(); c++; }
            });
            return c;
        }""")
        print(f"Checked {checked} checkboxes")
        await page.wait_for_timeout(1000)

        print("=== STEP 8: Submit (NOT clicking - just capturing state) ===")
        # DON'T actually submit — just capture what would be sent
        final_state = await page.evaluate("""() => {
            const radios = [...document.querySelectorAll('input[type="radio"]:checked')];
            const cbs = [...document.querySelectorAll('input[type="checkbox"]:checked')];
            const btn = document.querySelector('button[name="finish"]');
            const forms = [...document.querySelectorAll('form')].map(f => ({action: f.action, method: f.method, id: f.id, inputs: [...f.querySelectorAll('input,select,textarea')].map(i => ({name: i.name, type: i.type, value: i.value?.substring(0,100), checked: i.checked}))}));
            return {
                url: window.location.href,
                radios: radios.map(r => ({name: r.name, value: r.value, id: r.id})),
                checkboxes: cbs.map(c => ({name: c.name, id: c.id, value: c.value})),
                submitBtn: btn ? {text: btn.textContent.trim(), disabled: btn.disabled} : 'NOT_FOUND',
                forms: forms,
            };
        }""")
        print(f"Final state: {json.dumps(final_state, indent=2, ensure_ascii=False)}")

        # Filter requests to only relevant ones
        relevant = [r for r in requests_log if any(kw in r["url"] for kw in ['/cart', '/order', '/login', 'payment', 'delivery', 'shipment', '/api'])]

        result = {
            "final_state": final_state,
            "relevant_requests": relevant,
            "all_requests_count": len(requests_log),
        }

        OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        print(f"\n=== DONE: {len(relevant)} relevant requests captured ===")
        print(f"Output: {OUTPUT}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
