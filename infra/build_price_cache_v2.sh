#!/bin/bash
# Build price cache — one request at a time, restart FS between batches of 5
# Works around FS OOM by not letting Chrome accumulate
cd /opt/pokemon-monitor-v2

echo "=== BUILD PRICE CACHE v2 $(date) ==="

# Get set numbers from limango (fast, no FS needed)
SETS=$(./venv/bin/python3 -c "
import asyncio,re,json,ssl,aiohttp
async def main():
    ssl_ctx=ssl.create_default_context(); ssl_ctx.check_hostname=False; ssl_ctx.verify_mode=ssl.CERT_NONE
    HEADERS={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    SITEMAP_URLS=[f'https://klockoradar.pl/sitemap/{i}.xml' for i in range(8)]
    STOP_WORDS={'lego','the','and','with','in','of','for','to','a','an','w','i','z','do','na','od','dla','set','r','from'}
    sitemap={}
    async with aiohttp.ClientSession(headers=HEADERS) as s:
        for url in SITEMAP_URLS:
            try:
                async with s.get(url,timeout=aiohttp.ClientTimeout(total=30)) as r:
                    xml=await r.text()
                for m in re.findall(r'klockoradar\.pl/sets/(\d+)-([^<]+)</loc>',xml): sitemap[m[0]]=m[1]
            except: pass
    BASE='https://www.limango.pl'
    sets={}
    async with aiohttp.ClientSession(headers=HEADERS) as s:
        for page in range(1,7):
            url=f'{BASE}/shop/lego?page={page}' if page>1 else f'{BASE}/shop/lego'
            try:
                async with s.get(url,timeout=aiohttp.ClientTimeout(total=30),ssl=ssl_ctx) as r: html=await r.text()
                match=re.search(r'<script\s+id=\"__NEXT_DATA__\"[^>]*>(.*?)</script>',html,re.DOTALL)
                if not match: break
                data=json.loads(match.group(1))
                for item in data['props']['pageProps']['preloadedState']['listing']['products']['data']:
                    name=item.get('name','')
                    m=re.search(r'\b(\d{5})\b',name)
                    if m: sets[m.group(1)]=name
                    else:
                        words=set(re.sub(r'[^a-z0-9\s]',' ',name.lower().replace('\u00ae','').replace('\u2122','')).split())-STOP_WORDS
                        words={w for w in words if len(w)>1}
                        best_n=None;best_s=0
                        for num,slug in sitemap.items():
                            sw=set(slug.split('-'))-STOP_WORDS; sw={w for w in sw if len(w)>1}
                            sc=len(words&sw)
                            if sc>best_s: best_s=sc;best_n=num
                        if best_s>=2: sets[best_n]=name
                        elif best_s==1:
                            ms=words&set(sitemap.get(best_n,'').split('-'))
                            for w in ms:
                                if len(w)>=8: sets[best_n]=name;break
            except: break
    for num in sorted(sets): print(num)
asyncio.run(main())
" 2>/dev/null)

TOTAL=$(echo "$SETS" | wc -l)
echo "Found $TOTAL set numbers to fetch"
echo ""

# Fetch prices one by one, restart FS every 5 requests
COUNT=0
CACHE_FILE="data/price_cache.json"
echo "{" > "$CACHE_FILE"
FIRST=1

for NUM in $SETS; do
    COUNT=$((COUNT+1))
    
    # Restart FS every 5 requests (prevents OOM)
    if [ $((COUNT % 5)) -eq 1 ] && [ $COUNT -gt 1 ]; then
        docker restart flaresolverr >/dev/null 2>&1
        sleep 8
    fi
    
    # Fetch from promoklocki via FS
    RESPONSE=$(curl -s -X POST http://localhost:8191/v1 \
        -H "Content-Type: application/json" \
        -d "{\"cmd\":\"request.get\",\"url\":\"https://promoklocki.pl/$NUM\",\"maxTimeout\":30000}" \
        --max-time 40 2>/dev/null)
    
    PRICE=$(echo "$RESPONSE" | python3 -c "
import sys,json,re
try:
    d=json.load(sys.stdin)
    h=d.get('solution',{}).get('response','')
    m=re.search(r'najni.sza.{0,100}?([\d]+[.,][\d]+)\s*z',h,re.I)
    if m: print(m.group(1).replace(',','.'))
    else: print('')
except: print('')
" 2>/dev/null)
    
    if [ -n "$PRICE" ] && [ "$PRICE" != "" ]; then
        if [ $FIRST -eq 0 ]; then echo "," >> "$CACHE_FILE"; fi
        FIRST=0
        NOW=$(date '+%Y-%m-%d %H:%M:%S')
        NOWTS=$(date +%s)
        echo "  \"$NUM\": {\"set_number\":\"$NUM\",\"lowest_price\":$PRICE,\"promoklocki_url\":\"https://promoklocki.pl/$NUM\",\"updated_at\":\"$NOW\",\"updated_at_ts\":$NOWTS}" >> "$CACHE_FILE"
        echo "  [$COUNT/$TOTAL] #$NUM: ${PRICE} zl"
    else
        echo "  [$COUNT/$TOTAL] #$NUM: FAIL"
    fi
    
    sleep 5
done

echo "" >> "$CACHE_FILE"
echo "}" >> "$CACHE_FILE"

CACHED=$(grep -c "lowest_price" "$CACHE_FILE")
echo ""
echo "=== DONE: $CACHED prices cached ==="
