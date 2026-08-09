"""Empik scraper - capsolver CF bypass + aiohttp (no Chrome needed)"""
import asyncio
import os
import json
import logging
import re
import aiohttp
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("monitor")

CAPSOLVER_KEY = os.environ.get("CAPSOLVER_API_KEY", "")
PROXY_ADDR = os.environ.get("PROXY_ADDR", "127.0.0.1:8888")
SEARCH_URL = "https://www.empik.com/szukaj/produkt?q=pokemon+tcg&searchCategory=all&sort=publishDesc"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
EXCLUDE_KW = [
    "korea", "korean", "japan", "japanese", "kore", "japońsk", "jap",
    "deck", "battle deck", "league battle",
    "magazyn", "trenuj ze mn",
    "mata do gry", "playmat", "playmaty",
    "koszulki na karty", "sleeve", "battle box",
    "minimalistyczna mata",
]
MAX_PAGES = 3


async def _solve_cf(session, url):
    """Get cf_clearance cookie via capsolver AntiCloudflareTask."""
    if not CAPSOLVER_KEY:
        log.error("[empik] No CAPSOLVER_API_KEY set")
        return None, None

    proxy_str = PROXY_ADDR.replace("http://", "")

    # First get the challenge HTML via proxy
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
            "proxy": proxy_str,
            "userAgent": UA,
        }
    }
    if challenge_html and "Just a moment" in challenge_html:
        payload["task"]["html"] = challenge_html[:50000]

    try:
        async with session.post("https://api.capsolver.com/createTask", json=payload) as resp:
            data = await resp.json()
        task_id = data.get("taskId")
        if not task_id:
            log.error(f"[empik] capsolver createTask failed: {data}")
            return None, None

        # Poll for result (max 60s)
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
                log.error(f"[empik] capsolver failed: {result}")
                return None, None
    except Exception as e:
        log.error(f"[empik] capsolver error: {e}")

    return None, None


async def get_products():
    products = []
    seen_ids = set()

    async with aiohttp.ClientSession() as session:
        # Solve CF challenge
        cookies, user_agent = await _solve_cf(session, SEARCH_URL)
        if not cookies:
            log.error("[empik] Failed to get cf_clearance")
            return []

        cf_clearance = cookies.get("cf_clearance", "")
        if not cf_clearance:
            log.error("[empik] No cf_clearance in solution")
            return []

        headers = {"User-Agent": user_agent or UA}
        cookie_jar = {"cf_clearance": cf_clearance}

        for pg in range(1, MAX_PAGES + 1):
            url = SEARCH_URL if pg == 1 else f"{SEARCH_URL}&start={(pg - 1) * 60}"
            try:
                async with session.get(url,
                                       proxy=f"http://{PROXY_ADDR}",
                                       headers=headers,
                                       cookies=cookie_jar,
                                       timeout=aiohttp.ClientTimeout(total=30),
                                       ssl=False) as resp:
                    if resp.status != 200:
                        log.warning(f"[empik] Page {pg} status {resp.status}")
                        break
                    html = await resp.text()
            except Exception as e:
                log.error(f"[empik] Fetch page {pg}: {e}")
                break

            if "Just a moment" in html or len(html) < 5000:
                log.warning(f"[empik] CF still active on page {pg}")
                break

            soup = BeautifulSoup(html, "lxml")
            items = soup.select(".search-list-item")
            if not items:
                break

            for item in items:
                link = item.select_one('a[href*=",p"]')
                if not link:
                    continue
                href = link.get("href", "")
                pid_match = re.search(r',p(\d+),', href)
                if not pid_match:
                    continue
                pid = pid_match.group(1)
                if pid in seen_ids:
                    continue

                title_el = item.select_one("h2.product-title, .product-title")
                name = title_el.get_text(strip=True) if title_el else ""
                if not name:
                    continue
                name_lower = name.lower()
                if any(kw in name_lower for kw in EXCLUDE_KW):
                    continue

                seen_ids.add(pid)
                price_el = item.select_one('.product-price__value, .price, [class*="price"]')
                price_text = price_el.get_text(strip=True) if price_el else ""
                price_match = re.search(r'([\d]+[,.]?[\d]*)\s*z', price_text)
                price_val = price_match.group(1).replace(',', '.') if price_match else ""
                price_str = f"{price_val} zl" if price_val else "brak"

                url_full = "https://www.empik.com" + href if not href.startswith("http") else href

                img_el = item.select_one("img")
                image = ""
                if img_el:
                    image = img_el.get("src") or img_el.get("data-src", "")

                mp_match = re.search(r'mpShopId=(\d+)', href)
                shop_id = mp_match.group(1) if mp_match else "0"
                stock_label = "empik" if shop_id == "0" else f"marketplace_{shop_id}"

                products.append({
                    "id": f"empik_{pid}",
                    "name": name,
                    "price": price_str,
                    "shop": "empik",
                    "url": url_full,
                    "image": image,
                    "stock": stock_label,
                    "available": bool(price_val),
                })

            if len(items) < 20:
                break

    log.info(f"[EMPIK] {len(products)} produktow")
    return products
