"""
Scraper: libristo.pl — behind Cloudflare
Method: patchright (persistent stealth browser) + BeautifulSoup
BROWSER_TYPE = "stealth"
"""
import asyncio
import re
import logging
import html as html_lib
from bs4 import BeautifulSoup

log = logging.getLogger("monitor")

SHOP = "libristo"
BROWSER_TYPE = "stealth"
BASE = "https://www.libristo.pl"
SEARCH_URL = f"{BASE}/pl/wyszukiwanie?t=Pokemon+tcg"

EXCLUDE = [
    "sleeves", "koszulk", "toploader", "album", "portfolio", "pro-binder",
    "playmat", "mata", "segregator", "deck box", "alcove", "ultra pro", "ultra-pro",
    "one piece", "lorcana", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "dragon shield", "weiss schwarz",
    "riftbound", "dragon ball", "force of will",
    "japonsk", "japońsk", "japanese", "japan", "(jp)", "japonský", "japonsky",
    "korean", "koreańsk", "chiński", "chinese", "(chi)",
    "battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "battle academy",
    "singl", "single", "grading", "psa ", "cgc ",
    "zeszyt", "puzzle", "figurk", "figure set", "plush",
    "wydarzen", "event", "turniej", "bilet", "wpisowe",
    "penál", "piórnik", "pencil", "backpack", "plecak",
    "back to school",
]


async def scan_with_page(page):
    """Persistent browser interface — page already exists, just navigate."""
    products = []
    seen = set()

    await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(12)

    # Check CF
    title = await page.title()
    if "moment" in (title or "").lower() or "checking" in (title or "").lower():
        log.warning("[libristo] CF challenge, waiting...")
        await asyncio.sleep(15)
        title = await page.title()

    html = await page.content()
    if not html or len(html) < 5000:
        log.error(f"[libristo] Empty/short HTML: {len(html) if html else 0}")
        return []

    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("div.shrink-0")

    for card in cards:
        link = card.select_one('a[href*="/pl/prasa/"]')
        if not link:
            continue

        href = link.get("href", "")
        if "pokemon" not in href.lower():
            continue

        pid_match = re.search(r"_(\d+)$", href.rstrip("/"))
        pid = pid_match.group(1) if pid_match else ""
        if not pid or pid in seen:
            continue
        seen.add(pid)

        # Name
        name = ""
        texts = [t.strip() for t in card.stripped_strings if len(t.strip()) > 15]
        if texts:
            name = texts[0]
        if not name:
            name = link.get("title", "").strip()
        if not name or len(name) < 15:
            continue

        name = html_lib.unescape(name)
        name_low = name.lower()

        if "pokemon" not in name_low and "pokémon" not in name_low:
            continue
        if any(ex in name_low for ex in EXCLUDE):
            continue

        # Price
        card_text = card.get_text(" ", strip=True)
        price = "brak"
        available = True
        all_texts = [t.strip() for t in card.stripped_strings]
        for t in all_texts:
            price_m = re.match(r"^(\d+[.,]\d{2})$", t)
            if price_m:
                val = price_m.group(1).replace(",", ".")
                try:
                    if float(val) > 0:
                        price = val + " zl"
                        break
                except ValueError:
                    pass
        if price == "brak":
            price_match = re.search(r"(\d+[.,]\d{2})\s*zł", card_text)
            if price_match:
                price = price_match.group(1).replace(",", ".") + " zl"

        # Price filter
        try:
            pv = float(price.replace(" zl", ""))
            if 0 < pv < 10:
                continue
            if pv == 0:
                price = "brak"
                available = False
        except (ValueError, AttributeError):
            pass

        # Image
        image = ""
        for img in card.select("img"):
            src = img.get("src", "") or img.get("data-src", "")
            if src and src.startswith("http") and "tag" not in src and "flag" not in src:
                image = src
                break

        # Availability
        avail_text = card_text.lower()
        if "niedost" in avail_text or "wyprzeda" in avail_text:
            available = False

        url = href if href.startswith("http") else BASE + href

        products.append({
            "id": f"libristo_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": url,
            "image": image,
            "stock": None,
            "available": available,
        })

    print(f"[LIBRISTO] {len(products)} produktow")
    return products


async def get_products():
    """Legacy interface — for testing only."""
    from patchright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"]
        )
        try:
            page = await browser.new_page()
            return await scan_with_page(page)
        finally:
            await browser.close()
