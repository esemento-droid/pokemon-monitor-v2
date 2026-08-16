"""
Scraper: libristo.pl (www.libristo.pl)
Platform: Custom (Libristo) behind Cloudflare
Method: nodriver (headless Chrome) + BeautifulSoup
Category: search?t=Pokemon+tcg
Note: CF blocks FlareSolverr, nodriver passes
"""
import asyncio
import re
import os
import logging
import html as html_lib
from bs4 import BeautifulSoup

log = logging.getLogger("monitor")

SHOP = "libristo"
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


async def get_products():
    import nodriver as uc

    products = []
    seen = set()

    try:
        browser = await uc.start(
            headless=False, sandbox=False,
            browser_args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--disable-setuid-sandbox"]
        )
    except Exception as e:
        log.error(f"[libristo] Failed to start browser: {e}")
        return []

    try:
        page = await browser.get(SEARCH_URL)
        print(f"[libristo] Page loaded, waiting 12s...", flush=True)
        await asyncio.sleep(12)

        # Check CF
        title = await page.evaluate("document.title")
        print(f"[libristo] Title: {title}", flush=True)
        if "moment" in (title or "").lower() or "checking" in (title or "").lower():
            log.warning("[libristo] CF challenge, waiting...")
            await asyncio.sleep(15)
            title = await page.evaluate("document.title")
            print(f"[libristo] Title after wait: {title}", flush=True)

        html = await page.evaluate("document.documentElement.outerHTML")
        if not html or len(html) < 5000:
            log.error(f"[libristo] Empty/short HTML response: {len(html) if html else 0}")
            print(f"[LIBRISTO] 0 produktow (CF block, html={len(html) if html else 0})")
            return []

        print(f"[libristo] HTML OK: {len(html)} chars", flush=True)

        soup = BeautifulSoup(html, "lxml")

        # Product cards
        cards = soup.select("div.shrink-0")

        for card in cards:
            link = card.select_one('a[href*="/pl/prasa/"]')
            if not link:
                continue

            href = link.get("href", "")
            if "pokemon" not in href.lower():
                continue

            # ID from URL
            pid_match = re.search(r"_(\d+)$", href.rstrip("/"))
            pid = pid_match.group(1) if pid_match else ""
            if not pid or pid in seen:
                continue
            seen.add(pid)

            # Name — from card text (first meaningful string > 15 chars)
            name = ""
            texts = [t.strip() for t in card.stripped_strings if len(t.strip()) > 15]
            if texts:
                name = texts[0]

            if not name:
                # Fallback: link title
                name = link.get("title", "").strip()

            if not name or len(name) < 15:
                continue

            name = html_lib.unescape(name)
            name_low = name.lower()

            # Must be Pokemon
            if "pokemon" not in name_low and "pokémon" not in name_low:
                continue

            # Exclude
            if any(ex in name_low for ex in EXCLUDE):
                continue

            # Price — from card texts (number like "25.98" or "149.00")
            card_text = card.get_text(" ", strip=True)
            price = "brak"
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
            # Fallback: regex on full text
            if price == "brak":
                price_match = re.search(r"(\d+[.,]\d{2})\s*zł", card_text)
                if price_match:
                    price = price_match.group(1).replace(",", ".") + " zl"

            # Skip if price < 10 PLN (singles)
            try:
                pv = float(price.replace(" zl", ""))
                if 0 < pv < 10:
                    continue
                # Price 0 = no price listed = unavailable preorder
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
            available = "niedost" not in avail_text and "wyprzeda" not in avail_text

            # Full URL
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

    except Exception as e:
        log.error(f"[libristo] Error: {e}")
    finally:
        try:
            browser.stop()
        except:
            pass

    print(f"[LIBRISTO] {len(products)} produktow")
    return products
