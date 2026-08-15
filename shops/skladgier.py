import asyncio
import json
import subprocess

COLLECTIONS = [
    "pokemon-ascended-heroes",
    "pokemon-black-bolt-white-flare",
    "pokemon-chaos-rising",
    "pokemon-destined-rivals",
    "pokemon-journey-together",
    "pokemon-mega-evolution",
    "pokemon-perfect-order",
    "pokemon-phantasmal-flames",
    "pokemon-pitch-black",
    "pokemon-prismatic-evolutions",
    "pokemon-surging-sparks",
    "pokemon-30th-celebration",
]
BASE = "https://skladgier.pl/collections/{}/products.json?limit=250"

EXCLUDE = ["battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "wcs ", "battle academy",
    "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean",
    "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "ultra pro", "ultra-pro", "playmat", "portfolio", "pro-binder",
    "sleeves", "toploader", "album", "koszulk", "segregator",
    "deck box", "alcove",
    "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto",
    "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz",
    "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"]


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
            purl = "https://skladgier.pl/products/" + p.get("handle","")
            if any(ex in name.lower() for ex in EXCLUDE): continue

            products.append({"id":f"skladgier_{pid}","name":name,"price":price,"shop":"skladgier","url":purl,"image":image,"stock":1 if available else 0,"available":available})
        await asyncio.sleep(0.5)
    return products
