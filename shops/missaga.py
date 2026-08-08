import aiohttp
from bs4 import BeautifulSoup
import re

BASE_URL = "https://missaga.pl/kategoria-produktu/karty-pokemon/angielskie/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

async def get_products():
    products = []
    seen_ids = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for page in range(1, 10):
            url = BASE_URL if page == 1 else f"{BASE_URL}page/{page}/"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200: break
                html = await resp.text()
            soup = BeautifulSoup(html, "lxml")
            prods = soup.select("li.product")
            if not prods: break
            for p in prods:
                link = p.select_one("a.woocommerce-LoopProduct-link, a")
                if not link: continue
                href = link.get("href","")
                pid_match = re.search(r"post-(\d+)", " ".join(p.get("class",[])))
                pid = pid_match.group(1) if pid_match else href
                if pid in seen_ids: continue
                seen_ids.add(pid)
                title_el = p.select_one(".woocommerce-loop-product__title, h2")
                name = title_el.text.strip() if title_el else ""
                price_el = p.select_one(".price .amount, .price")
                price = price_el.text.strip().replace(" ","").replace(",",".").replace("zl"," PLN").replace("zł"," PLN") if price_el else "brak"
                img_el = p.select_one("img")
                image = img_el.get("src","") if img_el else ""
                classes = " ".join(p.get("class",[]))
                available = "outofstock" not in classes
                products.append({"id":f"missaga_{pid}","name":name,"price":price,"shop":"missaga","url":href,"image":image,"stock":1 if available else 0,"available":available})
            nxt = soup.select_one("a.next")
            if not nxt: break
    return products
