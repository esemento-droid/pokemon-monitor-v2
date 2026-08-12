"""
Price Compare Module — porównanie cen LEGO z KlockoRadar.pl
Sitemap -> 11000+ sets, /sets/{num} -> JSON-LD lowPrice
Fuzzy matching nazw -> numery setow -> ceny
"""
import asyncio,re,json,time,logging
from typing import Optional
import aiohttp

logger=logging.getLogger("monitor")

_sitemap_cache={}
_sitemap_last_fetch=0
SITEMAP_TTL=6*3600
_price_cache={}
PRICE_TTL=3600
KLOCKORADAR_BASE="https://klockoradar.pl"
SITEMAP_URLS=[f"{KLOCKORADAR_BASE}/sitemap/{i}.xml" for i in range(8)]
HEADERS={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
STOP_WORDS={"lego","the","and","with","in","of","for","to","a","an","w","i","z","do","na","od","dla","set","r","from"}

async def _load_sitemap(session):
    global _sitemap_cache,_sitemap_last_fetch
    if _sitemap_cache and (time.time()-_sitemap_last_fetch)<SITEMAP_TTL:
        return _sitemap_cache
    sets={}
    for url in SITEMAP_URLS:
        try:
            async with session.get(url,timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status!=200: continue
                xml=await resp.text()
            for m in re.findall(r'klockoradar\.pl/sets/(\d+)-([^<]+)</loc>',xml):
                sets[m[0]]=m[1]
        except: continue
    if sets:
        _sitemap_cache=sets
        _sitemap_last_fetch=time.time()
        logger.info(f"[PRICE] Loaded {len(sets)} sets from klockoradar")
    return _sitemap_cache

def _normalize_name(name):
    name=name.lower().replace("\u00ae","").replace("(r)","")
    name=re.sub(r'[^a-z0-9\s]',' ',name)
    words=set(name.split())-STOP_WORDS
    return {w for w in words if len(w)>1}

def match_set_number(product_name,sitemap):
    name_words=_normalize_name(product_name)
    if not name_words: return None
    best_num=None; best_score=0
    for num,slug in sitemap.items():
        slug_words=set(slug.split('-'))-STOP_WORDS
        slug_words={w for w in slug_words if len(w)>1}
        score=len(name_words&slug_words)
        if score>best_score:
            best_score=score; best_num=num
    return best_num if best_score>=2 else None

async def _fetch_price(session,set_number):
    global _price_cache
    cached=_price_cache.get(set_number)
    if cached and (time.time()-cached.get("fetched_at",0))<PRICE_TTL:
        return cached
    url=f"{KLOCKORADAR_BASE}/sets/{set_number}"
    try:
        async with session.get(url,timeout=aiohttp.ClientTimeout(total=15),headers=HEADERS) as resp:
            if resp.status!=200: return None
            html=await resp.text()
    except: return None
    for ld_raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>',html,re.DOTALL):
        try: data=json.loads(ld_raw)
        except: continue
        if data.get("@type")!="Product": continue
        offers=data.get("offers",{})
        if offers.get("@type")=="AggregateOffer":
            low=offers.get("lowPrice")
            if low is None: continue
            low=float(low)
            shop_name=""; shop_url=""
            individual=offers.get("offers",[])
            if individual:
                cheapest=min(individual,key=lambda o:float(o.get("price",99999)))
                shop_name=cheapest.get("seller",{}).get("name","")
                shop_url=cheapest.get("url","")
            result={"set_number":set_number,"lowest_price":low,"shop":shop_name,"shop_url":shop_url,"offer_count":offers.get("offerCount",0),"klockoradar_url":url,"fetched_at":time.time()}
            _price_cache[set_number]=result
            return result
    return None

async def get_price_comparison(product_name,product_price,session=None):
    own=session is None
    if own: session=aiohttp.ClientSession(headers=HEADERS)
    try:
        sitemap=await _load_sitemap(session)
        if not sitemap: return None
        set_number=match_set_number(product_name,sitemap)
        if not set_number: return None
        price_data=await _fetch_price(session,set_number)
        if not price_data: return None
        lowest=price_data["lowest_price"]
        diff=product_price-lowest
        pct=(diff/lowest)*100 if lowest>0 else 0
        return {"set_number":price_data["set_number"],"lowest_price":lowest,"shop":price_data["shop"],"shop_url":price_data.get("shop_url",""),"offer_count":price_data.get("offer_count",0),"klockoradar_url":price_data.get("klockoradar_url",""),"difference":round(diff,2),"percentage":round(pct,1),"is_cheaper":diff<0}
    finally:
        if own: await session.close()

def format_price_comparison(comparison):
    if not comparison: return ""
    lowest=comparison["lowest_price"]
    diff=comparison["difference"]
    pct=comparison["percentage"]
    shop=comparison["shop"]
    if diff<0:
        return f"\u2705 TANIEJ o {abs(diff):.2f} zl ({pct:.0f}%) vs {shop} ({lowest:.2f} zl)"
    elif diff>0:
        return f"\u26a0\ufe0f DROZEJ o {diff:.2f} zl (+{pct:.0f}%) vs {shop} ({lowest:.2f} zl)"
    else:
        return f"\U0001f7f0 Taka sama cena jak {shop} ({lowest:.2f} zl)"

if __name__=="__main__":
    async def test():
        products=[
            ("LEGO Star Wars 501St Clone Troopers Battle Pack",72.95),
            ("LEGO Technic Koenigsegg Jesko Absolut",169.95),
            ("LEGO Icons Polaroid Onestep Sx 70",189.95),
            ("LEGO Creator Sunflowers",55.95),
            ("LEGO City F1 Garage With Mercedes Amg And Alpine Racing Cars",249.95),
            ("LEGO Technic Deep Sea Research Submarine",134.95),
        ]
        async with aiohttp.ClientSession(headers=HEADERS) as s:
            sitemap=await _load_sitemap(s)
            print(f"Sitemap: {len(sitemap)} sets\n")
            for name,price in products:
                r=await get_price_comparison(name,price,s)
                if r:
                    fmt=format_price_comparison(r)
                    print(f"  {name[:50]} | {price} zl")
                    print(f"    Set #{r['set_number']} | {fmt}")
                else:
                    sn=match_set_number(name,sitemap)
                    print(f"  {name[:50]} -> NO DATA (match={sn})")
                print()
    asyncio.run(test())
