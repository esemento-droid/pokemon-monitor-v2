#!/usr/bin/env python3
"""
Test: pre-staged /order + API cart swap + submit WITHOUT reload.
Also test: how fast can we poll stock via API.

Scenario:
1. Login, ATC Mini Tin (available), go to /order, stage checkout
2. API: clear cart + ATC different product (control: also available)
3. Click submit WITHOUT reload — does it order the NEW product?
4. Bonus: measure stock poll speed via API
"""
import asyncio
import time
import json
from patchright.async_api import async_playwright

SHOP = "https://japancollectibles.shop"
PROXY = {"server": "http://127.0.0.1:8888"}
EMAIL = "t11008543@gmail.com"
PASS = "mt!cSsphud4Zhnz"

# Stage with this product (available, cheap):
STAGE_PID = 7437  # Mini Tin 70 PLN

# Swap to this product (also available, different):
SWAP_PID = 7589  # Kanto Friends Mini Tin 80 PLN

# OOS product to test poll:
POLL_PID = 9419  # Pakiet 30th


async def main():
    t0 = time.time()
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        proxy=PROXY,
    )
    ctx = await browser.new_context(viewport={"width": 1280, "height": 900}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
    page = await ctx.new_page()

    # === 1. LOGIN ===
    await page.goto(f"{SHOP}/login", wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(2000)
    await page.evaluate("""() => { document.getElementById('cc--main')?.remove(); document.querySelector('.skyshop-alert-conditional-access button')?.click(); }""")
    await page.wait_for_timeout(1000)
    await page.fill("input#email", EMAIL)
    await page.fill("input[name='password']", PASS)
    await page.click("button[name='submit']", force=True)
    await page.wait_for_timeout(3000)
    print(f"1. Login: {time.time()-t0:.1f}s")

    # === 2. ATC STAGE product (browser click) ===
    await page.goto(f"{SHOP}/Pokemon-TCG-Angielski-Mega-Heroes-Mini-Tin-p{STAGE_PID}", wait_until="domcontentloaded", timeout=15000)
    await page.wait_for_timeout(2000)
    await page.evaluate("""() => { document.getElementById('cc--main')?.remove(); document.querySelector('.fixed-elements')?.remove(); }""")
    atc = page.locator("button:has-text('Do koszyka')").first
    await atc.wait_for(state="visible", timeout=8000)
    await atc.click(force=True)
    await page.wait_for_timeout(2000)
    try:
        r = page.locator("text=Realizuj zamówienie")
        if await r.is_visible(timeout=2000):
            await r.click()
    except:
        pass
    print(f"2. ATC stage product {STAGE_PID}: {time.time()-t0:.1f}s")

    # === 3. GO TO /order, stage checkout ===
    await page.goto(f"{SHOP}/cart/", wait_until="domcontentloaded", timeout=15000)
    await page.wait_for_timeout(3000)
    await page.evaluate("""() => { document.getElementById('cc--main')?.remove(); document.querySelector('.fixed-elements')?.remove(); }""")
    checkout = page.locator("button[data-ng-click='order()']:not([disabled])")
    await checkout.wait_for(state="visible", timeout=15000)
    await checkout.click(force=True)
    await page.wait_for_url("**/order**", timeout=15000)
    await page.wait_for_timeout(3000)

    # Select BLIK
    await page.evaluate("""() => { document.getElementById('cc--main')?.remove(); document.querySelector('.fixed-elements')?.remove(); }""")
    for _ in range(10):
        has = await page.evaluate("() => document.body.innerText.includes('BLIK')")
        if has:
            break
        await page.wait_for_timeout(1500)
    blik = page.locator("text=BLIK").first
    await blik.wait_for(state="visible", timeout=10000)
    await blik.click(force=True)
    await page.wait_for_timeout(3000)

    # Select delivery
    for _ in range(10):
        has = await page.evaluate("() => document.body.innerText.includes('Kurier Inpost')")
        if has:
            break
        await page.wait_for_timeout(1500)
    try:
        d = page.locator("text=Kurier Inpost - Gabaryt C >> visible=true")
        if await d.count() > 0:
            await d.first.click(force=True)
        else:
            d = page.locator("input#param-delivery-6512b")
            if await d.count() > 0:
                await d.evaluate("el => el.closest('tr,div')?.click() || el.click()")
            else:
                await page.evaluate("""() => { const rows=document.querySelectorAll('tr,div,label'); for(const r of rows){if(r.textContent.includes('Kurier')&&r.textContent.includes('Inpost')){const radio=r.querySelector('input[type=radio]');if(radio)radio.click();else r.click();return;}} }""")
    except:
        pass
    await page.wait_for_timeout(1500)

    # Checkboxes
    await page.evaluate("""() => { window.scrollTo(0,document.body.scrollHeight); document.querySelectorAll('input[type=checkbox]').forEach(cb=>{if(cb.getAttribute('data-valid')?.includes('required')&&!cb.checked)cb.click();}); }""")
    await page.wait_for_timeout(500)

    print(f"3. Checkout STAGED on /order: {time.time()-t0:.1f}s")

    # Capture pre-swap state
    pre_state = await page.evaluate("""() => {
        const csrf = document.querySelector('input[name=csrf_token]')?.value || '';
        const btn = document.querySelector('button[name=finish]');
        const radios = [...document.querySelectorAll('input[type=radio]:checked')].map(r=>r.name+'='+r.value);
        const price = document.body.innerText.match(/Suma[:\\s]+(\\d[\\d\\s,]+zł)/)?.[1] || '?';
        return {csrf: csrf.substring(0,15)+'...', btn_disabled: btn?.disabled, radios, price};
    }""")
    print(f"   State before swap: {json.dumps(pre_state, ensure_ascii=False)}")

    # === 4. API CART SWAP (clear + add new product) — from browser JS ===
    t_swap = time.time()
    swap_result = await page.evaluate(f"""async () => {{
        const cartId = document.cookie.match(/sky2_cart_id=([^;]+)/)?.[1];
        if (!cartId) return {{error: 'no cart_id cookie'}};
        
        // Get current cart items
        const cartResp = await fetch('/proxy_public_api?endpoint=/sky2/api-public/carts/bulk/' + cartId, {{headers: {{'Accept':'application/json','currency':'PLN','lang':'pl'}}}});
        const cartData = await cartResp.json();
        const items = cartData.cart?.items || [];
        
        // Delete all items
        for (const item of items) {{
            await fetch('/proxy_public_api?endpoint=/sky2/api-public/carts/' + cartId + '/items/' + item.id, {{
                method: 'DELETE', headers: {{'Accept':'application/json','currency':'PLN','lang':'pl'}}
            }});
        }}
        
        // Add new product
        const atcResp = await fetch('/proxy_public_api?endpoint=/sky2/api-public/carts/' + cartId + '/items', {{
            method: 'POST',
            headers: {{'Content-Type':'application/json','Accept':'application/json','currency':'PLN','lang':'pl'}},
            body: JSON.stringify({{productId: {SWAP_PID}, quantity: 1, parameters: []}})
        }});
        const atcData = await atcResp.json();
        return {{
            cleared: items.length,
            atc_status: atcResp.status,
            added: !!atcData.addedCartItem,
            price: atcData.addedCartItem?.priceSummary?.final?.grossDisplay || '?',
            swap_time_ms: Date.now()
        }};
    }}""")
    swap_time = time.time() - t_swap
    print(f"4. API cart swap: {json.dumps(swap_result, ensure_ascii=False)} ({swap_time:.2f}s)")

    # === 5. CLICK SUBMIT without reload ===
    t_fire = time.time()
    
    # Check button state
    btn_state = await page.evaluate("""() => {
        const btn = document.querySelector('button[name=finish]');
        return {exists: !!btn, disabled: btn?.disabled, text: btn?.textContent?.trim()?.substring(0,20)};
    }""")
    print(f"5. Button after swap: {json.dumps(btn_state)}")

    if btn_state.get("exists") and not btn_state.get("disabled"):
        await page.click("button[name=finish]", force=True)
        await page.wait_for_timeout(5000)
        final_url = page.url
        fire_time = time.time() - t_fire
        success = any(kw in final_url.lower() for kw in ["blik", "tpay", "przelewy24", "potwierdzenie", "autopay", "pay"])
        print(f"6. SUBMIT: URL={final_url[:70]} | fire_time={fire_time:.2f}s | success={success}")
    else:
        print(f"6. Button NOT available after swap — Angular blocked it")

    # === BONUS: Stock poll speed test ===
    print(f"\n=== BONUS: Stock poll speed (product {POLL_PID}) ===")
    poll_times = []
    for i in range(5):
        tp = time.time()
        stock_result = await page.evaluate(f"""async () => {{
            const resp = await fetch('/proxy_public_api?endpoint=/sky2/api-public/carts/bulk/latest', {{headers: {{'Accept':'application/json','currency':'PLN','lang':'pl'}}}});
            return resp.status;
        }}""")
        poll_times.append(time.time() - tp)
    avg_poll = sum(poll_times) / len(poll_times)
    print(f"   5 polls: {[f'{t:.3f}s' for t in poll_times]}")
    print(f"   Average: {avg_poll:.3f}s per poll")
    
    # Check product availability directly
    avail_result = await page.evaluate(f"""async () => {{
        const resp = await fetch('/-p{POLL_PID}');
        const html = await resp.text();
        const hasCart = html.includes('Do koszyka');
        const hasOOS = html.includes('Produkt niedostępny') || html.includes('niedostępn');
        return {{hasCart, hasOOS, status: resp.status}};
    }}""")
    print(f"   Product {POLL_PID} availability: {json.dumps(avail_result)}")

    print(f"\nTOTAL: {time.time()-t0:.1f}s")
    await browser.close()


asyncio.run(main())
