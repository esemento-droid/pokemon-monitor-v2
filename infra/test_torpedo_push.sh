#!/bin/bash
cd /opt/pokemon-monitor-v2
./venv/bin/python3 -c "
import asyncio, aiohttp, json, re, time

SHOP='https://japancollectibles.shop'
PROXY='http://127.0.0.1:8888'
EMAIL='t11008543@gmail.com'
PASS='mt!cSsphud4Zhnz'
PID='7437'
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

async def full_test():
    t0=time.time()
    jar=aiohttp.CookieJar(unsafe=True)
    conn=aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=conn, cookie_jar=jar, headers={'User-Agent':UA}) as s:
        # 1. GET login page (csrf)
        r=await s.get(f'{SHOP}/login', proxy=PROXY, timeout=aiohttp.ClientTimeout(total=8))
        html=await r.text()
        csrf_login=re.search(r'name=\"csrf_token\"\s*value=\"([^\"]+)\"', html)
        csrf_login=csrf_login.group(1) if csrf_login else ''
        print(f'1. Login page csrf: {csrf_login[:20]}... ({time.time()-t0:.2f}s)')

        # 2. POST login
        r=await s.post(f'{SHOP}/login', data={'email':EMAIL,'password':PASS,'autologin':'1','csrf_token':csrf_login,'redirect':'','submit':'submit'}, proxy=PROXY, timeout=aiohttp.ClientTimeout(total=8), allow_redirects=True)
        html=await r.text()
        logged=('Moje konto' in html or 'Wyloguj' in html)
        print(f'2. Login: {\"OK\" if logged else \"FAIL\"} ({time.time()-t0:.2f}s)')
        print(f'   Cookies: {[c.key for c in jar]}')

        # 3. Get cart
        r=await s.get(f'{SHOP}/proxy_public_api?endpoint=/sky2/api-public/carts/bulk/latest', proxy=PROXY, timeout=aiohttp.ClientTimeout(total=5))
        cart=await r.json()
        cart_id=cart.get('cart',{}).get('id','')
        items=cart.get('cart',{}).get('items',[])
        print(f'3. Cart: {cart_id[:12]}... items={len(items)} ({time.time()-t0:.2f}s)')

        # 4. Clear cart
        for item in items:
            iid=item.get('id','')
            if iid:
                await s.delete(f'{SHOP}/proxy_public_api?endpoint=/sky2/api-public/carts/{cart_id}/items/{iid}', headers={'Accept':'application/json','currency':'PLN','lang':'pl'}, proxy=PROXY, timeout=aiohttp.ClientTimeout(total=3))
        if items: print(f'4. Cleared {len(items)} items')

        # 5. ATC
        jar.update_cookies({'sky2_cart_id':cart_id}, response_url=aiohttp.client.URL(SHOP))
        r=await s.post(f'{SHOP}/proxy_public_api?endpoint=/sky2/api-public/carts/{cart_id}/items', json={'productId':int(PID),'quantity':1,'parameters':[]}, headers={'Content-Type':'application/json;charset=UTF-8','Accept':'application/json','currency':'PLN','lang':'pl','Origin':SHOP,'Referer':f'{SHOP}/-p{PID}'}, proxy=PROXY, timeout=aiohttp.ClientTimeout(total=5))
        atc=await r.json()
        added=atc.get('addedCartItem',{})
        print(f'5. ATC: {\"OK\" if added else \"FAIL\"} price={added.get(\"priceSummary\",{}).get(\"final\",{}).get(\"grossDisplay\",\"?\")} ({time.time()-t0:.2f}s)')

        # 6. POST /order
        r=await s.post(f'{SHOP}/order', data={'cart_id':cart_id}, headers={'Content-Type':'application/x-www-form-urlencoded','Origin':SHOP,'Referer':f'{SHOP}/cart/','Accept':'text/html,*/*','Upgrade-Insecure-Requests':'1'}, proxy=PROXY, timeout=aiohttp.ClientTimeout(total=8), allow_redirects=True)
        order_html=await r.text()
        csrf=re.search(r'csrf_token[^>]*value=\"([a-f0-9]+)\"', order_html)
        csrf=csrf.group(1) if csrf else ''
        ships=re.findall(r'id=\"param-delivery-([^\"]+)\"', order_html)
        # Also search for shipment data in script tags
        ship_data=re.findall(r'\"shipments?\":\s*\[([^\]]{1,500})\]', order_html)
        # Find payment section  
        pay_section=order_html[order_html.find('payment'):order_html.find('payment')+500] if 'payment' in order_html else ''
        print(f'6. Order page: {len(order_html)}b csrf=\"{csrf[:15]}\" ships={ships[:3]} ({time.time()-t0:.2f}s)')
        print(f'   ship_data: {ship_data[:1]}')
        print(f'   Cookies now: {[c.key+\"=\"+c.value[:15] for c in jar]}')
        # Dump section with form action
        form_idx=order_html.find('order_finish')
        if form_idx>0: print(f'   form section: {order_html[form_idx-100:form_idx+200]}')
        # Try to find csrf in ANY location
        all_csrfs=re.findall(r'([a-f0-9]{50,80}\d{10})', order_html)
        if all_csrfs: print(f'   Possible csrf tokens: {all_csrfs[:3]}')

        # 7. Try submit with empty csrf (test if server validates)
        submit_data={'csrf_token':csrf,'payment':'21','shipment':ships[0] if ships else '','user_country':'PL','register_link_to_rules':'1','register_must_accept':'1','dotpay_rules_agreed':'1','is_js':'1','code_discount':'','gratis':'','user_note':''}
        print(f'7. Submitting: {json.dumps(submit_data)[:200]}')
        r=await s.post(f'{SHOP}/order_finish/', data=submit_data, headers={'Content-Type':'application/x-www-form-urlencoded','Origin':SHOP,'Referer':f'{SHOP}/order'}, proxy=PROXY, timeout=aiohttp.ClientTimeout(total=10), allow_redirects=True)
        final_url=str(r.url)
        final_text=await r.text()
        print(f'   Result: HTTP {r.status} URL={final_url[:80]}')
        print(f'   Body start: {final_text[:300]}')
        errors=re.findall(r'error[^>]*>([^<]+)', final_text[:3000], re.IGNORECASE)
        if errors: print(f'   Errors: {errors[:5]}')
        print(f'   TOTAL TIME: {time.time()-t0:.2f}s')

asyncio.run(full_test())
" > /tmp/torpedo_result.txt 2>&1
cp /tmp/torpedo_result.txt torpedo_test_output.txt
git add torpedo_test_output.txt 2>/dev/null; git commit -m "full debug output" && git push origin main
