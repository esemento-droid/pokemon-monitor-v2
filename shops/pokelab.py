import asyncio
import json
import subprocess

COLLECTIONS = ["boxy-blistry","elite-trainer-box","angielskie-booster-boxy"]
BASE = "https://poke-lab.pl/collections/{}/products.json?limit=250"

async def get_products():
    products = []
    seen_ids = set()
    for col in COLLECTIONS:
        url = BASE.format(col)
        try:
            result = subprocess.run(["curl","-s","--max-time","30","-H","User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",url], capture_output=True, text=True)
            data = json.loads(result.stdout)
        except Exception:
            continue
        for p in data.get("products",[]):
            pid = str(p["id"])
            if pid in seen_ids: continue
            seen_ids.add(pid)
            name = p.get("title","")
            variants = p.get("variants",[])
            if not variants: continue
            price = str(variants[0].get("price","0")) + " PLN"
            available = any(v.get("available",False) for v in variants)
            imgs = p.get("images",[])
            image = imgs[0]["src"] if imgs else ""
            purl = "https://poke-lab.pl/products/" + p.get("handle","")
            products.append({"id":f"pokelab_{pid}","name":name,"price":price,"shop":"pokelab","url":purl,"image":image,"stock":1 if available else 0,"available":available})
        await asyncio.sleep(1)
    return products
