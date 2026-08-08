#!/usr/bin/env python3
import asyncio,aiohttp,json,sys,re,logging,os
from datetime import datetime
logging.basicConfig(filename='/opt/pokemon-monitor-v2/kartexpol_autobuy.log',level=logging.INFO,format='%(asctime)s %(message)s')
log=logging.getLogger(__name__)
# --- Discord notifications ---
WEBHOOK_FILE_KARTEXPOL = "/opt/pokemon-monitor-v2/discord_webhook_kartexpol.txt"

async def send_discord_kartexpol(msg):
    try:
        if not os.path.exists(WEBHOOK_FILE_KARTEXPOL):
            return
        url = open(WEBHOOK_FILE_KARTEXPOL).read().strip()
        if not url:
            return
        async with aiohttp.ClientSession() as s:
            await s.post(url, json={"content": msg})
    except Exception as e:
        log.warning(f"Discord send failed: {e}")
# --- end Discord ---

BASE="https://www.kartexpol.pl"
ACCOUNTS=[
{"firstName":"Tomasz","lastName":"Szczepaniak","street":"Lesna 46a/2","postalCode":"62-069","city":"Paledzie","phone":"607183797","email":"esemento@gmail.com"},
{"firstName":"Natalia","lastName":"Szczepaniak","street":"Zgoda 30b","postalCode":"60-122","city":"Poznan","phone":"514635586","email":"blackmat36@gmail.com"},
{"firstName":"Jagoda","lastName":"Kaczmarek","street":"Bukowska 104a/7","postalCode":"60-397","city":"Poznan","phone":"535024946","email":"tjbtaniojuzbylo@gmail.com"},
{"firstName":"Miroslawa","lastName":"Szczepaniak","street":"Bukowska 104a/7","postalCode":"60-397","city":"Poznan","phone":"603466903","email":"y24015411@gmail.com"},
]

async def place_order(session,account,stock_items):
    name=f"{account['firstName']} {account['lastName']}"
    try:
        r=await session.post(f"{BASE}/api/basket/")
        d=await r.json()
        bid=d['basket']['_links']['clean']['href'].split('/')[-1]
        log.info(f"[{name}] Basket: {bid}")
        added=0
        for stock_id,prod_name in stock_items:
            r=await session.post(f"{BASE}/api/basket/{bid}/item/{stock_id}")
            if r.status==200:
                added+=1
                log.info(f"[{name}] Added: {prod_name} (stock {stock_id})")
            else:
                log.warning(f"[{name}] Fail add {prod_name}: {r.status}")
        if added==0:
            return False,"No products added"
        addr={"firstName":account["firstName"],"lastName":account["lastName"],"street":account["street"],"postalCode":account["postalCode"],"city":account["city"],"country_code":"PL","country_id":179,"phone":account["phone"],"email":account["email"]}
        r=await session.put(f"{BASE}/api/basket/{bid}/billing-address",json=addr)
        d=await r.json()
        if d.get('formErrors'):
            return False,f"Billing err: {d['formErrors']}"
        await session.put(f"{BASE}/api/basket/{bid}/shipping-address",json=addr)
        await session.put(f"{BASE}/api/basket/{bid}/shipping/11",json={})
        await session.put(f"{BASE}/api/basket/{bid}/payment/3/3:9",json={})
        await session.put(f"{BASE}/api/basket/{bid}/additional-fields",json={"2":"1"})
        r=await session.post(f"{BASE}/api/basket/{bid}/place-order",json={})
        d=await r.json()
        if d.get("isPlaced"):
            oid=d.get("orderId","?")
            log.info(f"[{name}] ORDER PLACED #{oid} ({added} products)")
            await send_discord_kartexpol(f"\u2705 **{name}** - zamowienie #{oid} ({added} produktow)")
            return True,oid
        else:
            flash=d.get("flashMessages",[])
            inv=d.get("basket",{}).get("invalidSections",{})
            log.error(f"[{name}] FAILED: {flash} {inv}")
            return False,f"{flash} {inv}"
    except Exception as e:
        log.error(f"[{name}] Exception: {e}")
        return False,str(e)

async def get_stock_id(session,product_id):
    try:
        r=await session.get(f"{BASE}/pl/p/-/{product_id}",allow_redirects=True)
        html=await r.text()
        m=re.search(r'"stock_id":\s*(\d+)',html)
        if m:return int(m.group(1))
        m=re.search(r'data-stock[_-]id["\s=:]+["\']?(\d+)',html)
        if m:return int(m.group(1))
        return None
    except:return None

async def buy_products(products):
    log.info(f"=== KARTEXPOL BUY: {len(products)} products ===")
    for p in products:
        log.info(f"  {p.get('name')} | {p.get('url')}")
    headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36","Accept":"application/json","Content-Type":"application/json"}
    async with aiohttp.ClientSession(headers=headers) as session:
        stock_items=[]
        for p in products:
            sid=p.get('stock_id')
            if not sid:
                pid_m=re.search(r'/(\d+)$',p.get('url',''))
                if pid_m:
                    pid=int(pid_m.group(1))
                    sid=await get_stock_id(session,pid)
                    if not sid:sid=pid
            if sid:
                stock_items.append((sid,p.get('name',f'product_{sid}')))
            else:
                log.warning(f"No stock_id for: {p.get('name')}")
        if not stock_items:
            log.error("No stock IDs, aborting")
            return
        log.info(f"Stock items: {stock_items}")
        results=[]
        for account in ACCOUNTS:
            ok,res=await place_order(session,account,stock_items)
            name=f"{account['firstName']} {account['lastName']}"
            print(f"[{'OK' if ok else 'FAIL'}] {name}: {res}",flush=True)
            results.append((name,ok,res))
            await asyncio.sleep(1)
    ok=sum(1 for _,s,_ in results if s)
    log.info(f"=== DONE: {ok}/4 orders ===")
    for n,s,r in results:
        log.info(f"  {n}: {'OK #'+str(r) if s else 'FAIL '+str(r)}")
    print(f"\n=== DONE: {ok}/4 orders placed ===",flush=True)
    # Discord summary
    lines = [f"  {n}: {'OK #'+str(r) if s else 'FAIL'}" for n,s,r in results]
    await send_discord_kartexpol(f"\U0001f6d2 **Kartexpol AutoBuy** - {ok}/4 zamowien\n" + "\n".join(lines))

if __name__=="__main__":
    if len(sys.argv)>1:
        items=[]
        for arg in sys.argv[1:]:
            try:
                sid=int(arg)
                items.append({"stock_id":sid,"name":f"Product (stock {sid})","url":""})
            except ValueError:
                items.append({"url":arg,"name":arg.split('/')[-1]})
        asyncio.run(buy_products(items))
    else:
        print("Usage: python kartexpol_autobuy.py <stock_id1> [stock_id2] ...")
        print("  or pass product URLs as arguments")
        sys.exit(1)
