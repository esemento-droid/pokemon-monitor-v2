#!/bin/bash
cd /opt/pokemon-monitor-v2

# Test: pre-staged /order + API ATC + just click submit
# Checks if Angular updates cart on /order page after API ATC without reload

DISPLAY=:99 ./venv/bin/python3 -c "
import asyncio, time, json
from patchright.async_api import async_playwright

SHOP='https://japancollectibles.shop'
PROXY={'server': 'http://127.0.0.1:8888'}
EMAIL='t11008543@gmail.com'
PASS='mt!cSsphud4Zhnz'
PID='7437'
URL='https://japancollectibles.shop/Pokemon-TCG-Angielski-Mega-Heroes-Mini-Tin-p7437'

async def test():
    t0=time.time()
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True, args=['--no-sandbox','--disable-dev-shm-usage','--disable-blink-features=AutomationControlled'], proxy=PROXY)
    ctx = await browser.new_context(viewport={'width':1280,'height':900}, user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
    page = await ctx.new_page()

    # === LOGIN ===
    await page.goto(f'{SHOP}/login', wait_until='domcontentloaded', timeout=20000)
    await page.wait_for_timeout(2000)
    await page.evaluate(\"\"\"() => { document.getElementById('cc--main')?.remove(); document.querySelector('.skyshop-alert-conditional-access button')?.click(); }\"\"\")
    await page.wait_for_timeout(1000)
    await page.fill('input#email', EMAIL)
    await page.fill('input[name=\"password\"]', PASS)
    await page.click('button[name=\"submit\"]', force=True)
    await page.wait_for_timeout(3000)
    print(f'1. Login: {time.time()-t0:.1f}s')

    # === ATC (browser click - works) ===
    await page.goto(URL, wait_until='domcontentloaded', timeout=15000)
    await page.wait_for_timeout(2000)
    await page.evaluate(\"\"\"() => { document.getElementById('cc--main')?.remove(); document.querySelector('.fixed-elements')?.remove(); }\"\"\")
    atc = page.locator(\"button:has-text('Do koszyka')\").first
    await atc.wait_for(state='visible', timeout=8000)
    await atc.click(force=True)
    await page.wait_for_timeout(2000)
    # Dismiss popup
    try:
        r = page.locator('text=Realizuj zamówienie')
        if await r.is_visible(timeout=2000): await r.click()
    except: pass
    print(f'2. ATC: {time.time()-t0:.1f}s')

    # === GO TO /order (full flow - stage it) ===
    await page.goto(f'{SHOP}/cart/', wait_until='domcontentloaded', timeout=15000)
    await page.wait_for_timeout(3000)
    await page.evaluate(\"\"\"() => { document.getElementById('cc--main')?.remove(); document.querySelector('.fixed-elements')?.remove(); }\"\"\")
    checkout = page.locator(\"button[data-ng-click='order()']:not([disabled])\")
    await checkout.wait_for(state='visible', timeout=15000)
    await checkout.click(force=True)
    await page.wait_for_url('**/order**', timeout=15000)
    await page.wait_for_timeout(3000)
    print(f'3. On /order page: {time.time()-t0:.1f}s')

    # === SELECT PAYMENT + DELIVERY + CHECKBOXES (stage) ===
    await page.evaluate(\"\"\"() => { document.getElementById('cc--main')?.remove(); document.querySelector('.fixed-elements')?.remove(); }\"\"\")
    for _ in range(10):
        has = await page.evaluate(\"() => document.body.innerText.includes('BLIK')\")
        if has: break
        await page.wait_for_timeout(1500)
    
    blik = page.locator('text=BLIK').first
    await blik.wait_for(state='visible', timeout=10000)
    await blik.click(force=True)
    await page.wait_for_timeout(3000)

    for _ in range(10):
        has = await page.evaluate(\"() => document.body.innerText.includes('Kurier Inpost')\")
        if has: break
        await page.wait_for_timeout(1500)
    
    # Delivery
    try:
        d = page.locator('text=Kurier Inpost - Gabaryt C >> visible=true')
        if await d.count() > 0: await d.first.click(force=True)
        else:
            d = page.locator('input#param-delivery-6512b')
            if await d.count() > 0: await d.evaluate(\"el => el.closest('tr,div')?.click() || el.click()\")
            else:
                d = page.locator(\"td:has-text('Kurier Inpost')\").first
                await d.click(force=True, timeout=5000)
    except:
        await page.evaluate(\"\"\"() => { const rows=document.querySelectorAll('tr,div,label'); for(const r of rows){if(r.textContent.includes('Kurier')&&r.textContent.includes('Inpost')){const radio=r.querySelector('input[type=radio]');if(radio)radio.click();else r.click();return;}} }\"\"\")
    
    await page.wait_for_timeout(1500)
    await page.evaluate(\"\"\"() => { window.scrollTo(0,document.body.scrollHeight); document.querySelectorAll('input[type=checkbox]').forEach(cb=>{if(cb.getAttribute('data-valid')?.includes('required')&&!cb.checked)cb.click();}); }\"\"\")
    await page.wait_for_timeout(500)
    print(f'4. Checkout STAGED (BLIK+delivery+checkboxes): {time.time()-t0:.1f}s')

    # === NOW: capture state (csrf, submit button) ===
    state = await page.evaluate(\"\"\"() => {
        const csrf = document.querySelector('input[name=csrf_token]')?.value || '';
        const btn = document.querySelector('button[name=finish]');
        const radios = [...document.querySelectorAll('input[type=radio]:checked')].map(r=>r.name+'='+r.value);
        return {csrf: csrf.substring(0,20), btn: btn?{disabled:btn.disabled}:'NOT_FOUND', radios, url: location.href};
    }\"\"\")
    print(f'5. Pre-submit state: {json.dumps(state)}')

    # === SIMULATE: clear cart, do API ATC, then just click submit ===
    # First delete from cart via page (simulate fresh state)
    await page.evaluate(\"\"\"() => { document.querySelectorAll('[data-click=deleteCartItem],.icon-close_24').forEach(b=>b.click()); }\"\"\")
    await page.wait_for_timeout(2000)
    print(f'6. Cart cleared on page: {time.time()-t0:.1f}s')

    # Now ATC again via page JavaScript (simulate API ATC)  
    # Use Sky-Shop internal API from browser context (same session!)
    atc_result = await page.evaluate(f\"\"\"async () => {{
        const resp = await fetch('/proxy_public_api?endpoint=/sky2/api-public/carts/' + document.cookie.match(/sky2_cart_id=([^;]+)/)?.[1] + '/items', {{
            method: 'POST',
            headers: {{'Content-Type':'application/json','Accept':'application/json','currency':'PLN','lang':'pl'}},
            body: JSON.stringify({{productId:{PID},quantity:1,parameters:[]}})
        }});
        const data = await resp.json();
        return {{status: resp.status, added: !!data.addedCartItem}};
    }}\"\"\")
    print(f'7. API ATC from browser JS: {json.dumps(atc_result)} ({time.time()-t0:.1f}s)')

    # === KEY TEST: can we just click submit NOW without reload? ===
    t_fire = time.time()
    
    # Check if submit button is still there and enabled
    btn_state = await page.evaluate(\"\"\"() => {
        const btn = document.querySelector('button[name=finish]');
        return btn ? {exists:true, disabled:btn.disabled, text:btn.textContent.trim().substring(0,20)} : {exists:false};
    }\"\"\")
    print(f'8. Submit button after API ATC: {json.dumps(btn_state)}')

    if btn_state.get('exists') and not btn_state.get('disabled'):
        # CLICK SUBMIT!
        await page.click('button[name=finish]', force=True)
        await page.wait_for_timeout(5000)
        final_url = page.url
        fire_time = time.time() - t_fire
        print(f'9. SUBMIT RESULT: URL={final_url[:60]} | fire_time={fire_time:.2f}s')
        
        success = any(kw in final_url.lower() for kw in ['blik','tpay','przelewy24','potwierdzenie','thank'])
        print(f'10. SUCCESS: {success}')
    else:
        print(f'9. Submit button not available — need reload')
        # Try reload and submit
        await page.reload(wait_until='domcontentloaded', timeout=10000)
        await page.wait_for_timeout(5000)
        btn2 = await page.evaluate(\"\"\"() => { const b=document.querySelector('button[name=finish]'); return b?{disabled:b.disabled}:'NOT_FOUND'; }\"\"\")
        print(f'10. After reload: btn={json.dumps(btn2)}')

    print(f'TOTAL: {time.time()-t0:.1f}s')
    await browser.close()

asyncio.run(test())
" > /tmp/torpedo_result.txt 2>&1
cp /tmp/torpedo_result.txt torpedo_test_output.txt
git add torpedo_test_output.txt 2>/dev/null; git commit -m "test output" && git push origin main
