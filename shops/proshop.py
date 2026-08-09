"""Proshop.pl scraper - capsolver CF bypass + aiohttp (no Chrome needed)"""
import asyncio
import os
import re
import json
import logging
import aiohttp
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("monitor")

SHOP = "proshop"
URL = "https://www.proshop.pl/Pokemon"
CAPSOLVER_KEY = os.environ.get("CAPSOLVER_API_KEY", "")
PROXY_ADDR = os.environ.get("PROXY_ADDR", "127.0.0.1:8888")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
EXCLUDE = ["portfolio", "album", "sleeve", "koszulk", "toploader", "binder", "ultra pro",
           "ultrapro", "plush", "figure", "figurk", "playset", "carry case", "clip", "play 'n",
           "playmat", "mata ", "puzzle", "lego"]


async def _solve_cf(session, url):
    """Get cf_clearance cookie via capsolver AntiCloudflareTask."""
    if not CAPSOLVER_KEY:
        log.error("[proshop] No CAPSOLVER_API_KEY set")
        return None, None

    proxy_str = PROXY_ADDR.replace("http://", "")

    # Get challenge HTML
    challenge_html = ""
    try:
        async with session.get(url, proxy=f"http://{PROXY_ADDR}",
                               headers={"User-Agent": UA},
                               timeout=aiohttp.ClientTimeout(total=15),
                               ssl=False) as resp:
            challenge_html = await resp.text()
    except:
        pass

    payload = {
        "clientKey": CAPSOLVER_KEY,
        "task": {
            "type": "AntiCloudflareTask",
            "websiteURL": url,
            
            "userAgent": UA,
        }
    }
    if challenge_html and ("Just a moment" in challenge_html or "Attention Required" in challenge_html):
        payload["task"]["html"] = challenge_html[:50000]

    try:
        async with session.post("https://api.capsolver.com/createTask", json=payload) as resp:
            data = await resp.json()
        task_id = data.get("taskId")
        if not task_id:
            log.error(f"[proshop] capsolver createTask failed: {data}")
            return None, None

        for _ in range(30):
            await asyncio.sleep(2)
            async with session.post("https://api.capsolver.com/getTaskResult",
                                    json={"clientKey": CAPSOLVER_KEY, "taskId": task_id}) as resp:
                result = await resp.json()
            if result.get("status") == "ready":
                solution = result.get("solution", {})
                cookies = solution.get("cookies", {})
                user_agent = solution.get("userAgent", UA)
                return cookies, user_agent
            if result.get("status") == "failed":
                log.error(f"[proshop] capsolver failed: {result}")
                return None, None
    except Exception as e:
        log.error(f"[proshop] capsolver error: {e}")

    return None, None


async def get_products():
    products = []

    async with aiohttp.ClientSession() as session:
        cookies, user_agent = await _solve_cf(session, URL)
        if not cookies:
            log.error("[proshop] Failed to get cf_clearance")
            return []

        cf_clearance = cookies.get("cf_clearance", "")
        if not cf_clearance:
            log.error("[proshop] No cf_clearance in solution")
            return []

        headers = {"User-Agent": user_agent or UA}
        cookie_jar = {"cf_clearance": cf_clearance}

        try:
            async with session.get(URL,
                                   proxy=f"http://{PROXY_ADDR}",
                                   headers=headers,
                                   cookies=cookie_jar,
                                   timeout=aiohttp.ClientTimeout(total=30),
                                   ssl=False) as resp:
                if resp.status != 200:
                    log.error(f"[proshop] Status {resp.status} after CF solve")
                    return []
                html = await resp.text()
        except Exception as e:
            log.error(f"[proshop] Fetch error: {e}")
            return []

        if "Just a moment" in html or "Attention Required" in html:
            log.error("[proshop] CF still active after solve")
            return []

        soup = BeautifulSoup(html, "lxml")
        items = soup.select("li.site-productlist-item")
        if not items:
            # Try alternative selectors
            items = soup.select("[data-product-id], .product-list-item")

        seen = set()
        for item in items:
            name_el = item.select_one("h2[product-display-name], h2, h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name or len(name) < 5:
                continue
            if any(ex in name.lower() for ex in EXCLUDE):
                continue

            pid_el = item.select_one("input[name=productId], [data-product-id]")
            pid = ""
            if pid_el:
                pid = pid_el.get("value", "") or pid_el.get("data-product-id", "")
            if not pid or pid in seen:
                continue
            seen.add(pid)

            price_el = item.select_one(".site-currency-lg, [class*='price']")
            price = "brak"
            if price_el:
                pt = price_el.get_text(strip=True)
                pm = re.search(r"([\d,.]+)", pt)
                if pm:
                    price = pm.group(1).replace(".", "").replace(",", ".") + " zl"

            link = item.select_one("a.site-product-link, a[href]")
            href = ""
            if link:
                h = link.get("href", "")
                href = "https://www.proshop.pl" + h if h.startswith("/") else h

            btn = item.select_one("button.site-btn-green, [class*='add-to-cart']")
            available = btn is not None

            img = item.select_one("img[src]")
            image = ""
            if img:
                src = img.get("src", "")
                if src.startswith("/"):
                    image = "https://www.proshop.pl" + src
                else:
                    image = src

            products.append({
                "id": f"proshop_{pid}",
                "name": name,
                "price": price,
                "shop": SHOP,
                "url": href,
                "image": image,
                "stock": None,
                "available": available,
            })

    print(f"[PROSHOP] {len(products)} produktow")
    return products
