import aiohttp

API_URL = "https://dropnews.pl/wp-json/wc/store/v1/products?category=pokemon-tcg&per_page=100"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

async def get_products():
    products = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(API_URL, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200: return products
            data = await resp.json()
    for p in data:
        pid = str(p["id"])
        name = p.get("name","")
        price_raw = p.get("prices",{}).get("price","0")
        price = str(int(price_raw)/100) + " PLN" if price_raw else "brak"
        available = p.get("is_in_stock", False)
        if any(x in name.lower() for x in ["portfolio","album","pro-binder","ultra pro","ultra-pro","playmat","sleeves","toploader","koszulk","segregator","deck box","alcove","battle deck","league battle","rival battle","v battle","world championship","wcs deck","battle academy","japoński","japońsk","japanese","(jp)","koreański","korean","chiński","chinese","(chi)","lorcana","one piece","yu-gi-oh","digimon","naruto","star wars","magic the gathering","dragon shield","zeszyt","puzzle","figurk","figure set"]): continue
        link = p.get("permalink","")
        imgs = p.get("images",[])
        image = imgs[0]["src"] if imgs else ""
        products.append({"id":f"dropnews_{pid}","name":name,"price":price,"shop":"dropnews","url":link,"image":image,"stock":1 if available else 0,"available":available})
    return products
