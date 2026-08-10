"""
Scraper: mediaexpert.pl
Silnik: nodriver (Cloudflare bypass required)
Metoda: headless Chrome + mobile proxy
Szukaj: "pokemon tcg" - sealed products only
Filtr: TYLKO produkty sprzedawane przez Media Expert (nie marketplace)
Wykluczenia: deck, singles, Japanese, accessories
"""
import asyncio
import os
import json
import logging
import re

# Ensure DISPLAY is set for headless Chrome (Xvfb)
if not os.environ.get("DISPLAY"):
    os.environ["DISPLAY"] = ":99"

log = logging.getLogger("monitor")

SEARCH_URLS = [
    "https://www.mediaexpert.pl/szukaj-pokemon+tcg",
    "https://www.mediaexpert.pl/szukaj-pokemon+booster",
]

EXCLUDE_KW = [
    # Language/region
    "korea", "korean", "japan", "japanese", "kore", "japońsk", "jap",
    # Decks (user does NOT want decks)
    "deck", "battle deck", "league battle", "starter deck", "theme deck",
    # Singles / accessories
    "singiel", "single", "karta pojedyncza",
    "mata do gry", "playmat", "playmaty",
    "koszulki na karty", "sleeve", "sleeves",
    "album", "segregator", "binder", "portfolio",
    "toploader", "top loader",
    # Other non-sealed
    "figurka", "figure", "plush", "maskotka", "puzzle",
    "lego", "mega construx",
    "gra nintendo", "gra switch", "switch",
    "klaser", "piórnik",
]

# Keywords that MUST appear (at least one) to confirm it's Pokemon TCG sealed
INCLUDE_KW = [
    "booster", "etb", "elite trainer", "tin", "puszka",
    "box", "collection", "kolekcja", "zestaw", "bundle",
    "blister", "pack", "display", "karty pokemon",
    "tcg", "poke ball", "pokeball",
]

MAX_PAGES = 3
PROXY_ADDR = os.environ.get("PROXY_ADDR", "127.0.0.1:8888")

# JavaScript to extract products from Media Expert search results
EXTRACT_JS = """
JSON.stringify((function(){
    const result = [];
    // Media Expert uses .offer-box or product tiles
    const items = document.querySelectorAll('[data-product-id], .offer-box, .product-box, [class*="ProductCard"], [class*="product-card"]');
    
    for (const item of items) {
        try {
            // Product ID
            let pid = item.getAttribute('data-product-id') || '';
            
            // Name
            const nameEl = item.querySelector('h2, h3, [class*="name"], [class*="Name"], [class*="title"], [class*="Title"], a[title]');
            const name = nameEl ? (nameEl.textContent || nameEl.getAttribute('title') || '').trim() : '';
            if (!name) continue;
            
            // URL  
            const linkEl = item.querySelector('a[href*="/produkt/"], a[href*="/product/"]');
            let url = '';
            if (linkEl) {
                url = linkEl.getAttribute('href') || '';
                // Extract pid from URL if not found via attribute
                if (!pid) {
                    const pidMatch = url.match(/-(\\d+)\\.html/) || url.match(/\\/(\\d+)$/);
                    if (pidMatch) pid = pidMatch[1];
                }
            }
            if (!pid) {
                // Generate from name hash
                pid = name.replace(/[^a-z0-9]/gi, '').slice(0, 20);
            }
            
            // Price
            const priceEl = item.querySelector('[class*="price"] [class*="whole"], [class*="Price"], .price, [data-price]');
            let price = '';
            if (priceEl) {
                price = priceEl.textContent.trim().replace(/\\s+/g, ' ');
            }
            // Try data-price attribute
            if (!price) {
                const dpEl = item.querySelector('[data-price]');
                if (dpEl) price = dpEl.getAttribute('data-price');
            }
            
            // Image
            const imgEl = item.querySelector('img[src], img[data-src]');
            let image = '';
            if (imgEl) {
                image = imgEl.getAttribute('src') || imgEl.getAttribute('data-src') || '';
            }
            
            // Availability - check for "niedostepny" or "brak"
            const itemText = item.innerText.toLowerCase();
            const unavailable = itemText.includes('niedostępny') || itemText.includes('brak w magazynie') || itemText.includes('wycofany');
            
            // Seller info - check if it's Media Expert or marketplace
            // Media Expert own products don't show a seller name, marketplace shows "Sprzedawca:" 
            const sellerEl = item.querySelector('[class*="seller"], [class*="Seller"], [class*="marketplace"], [class*="vendor"]');
            const sellerText = sellerEl ? sellerEl.textContent.trim().toLowerCase() : '';
            const isMarketplace = sellerText && !sellerText.includes('media expert');
            
            if (url && !url.startsWith('http')) {
                url = 'https://www.mediaexpert.pl' + url;
            }
            
            result.push({
                pid: pid,
                name: name,
                price: price,
                url: url,
                image: image,
                available: !unavailable,
                isMarketplace: isMarketplace,
                sellerText: sellerText
            });
        } catch(e) {}
    }
    return result;
})())
"""

# Alternative extraction via JSON-LD (structured data)
JSONLD_EXTRACT_JS = """
JSON.stringify((function(){
    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
    const results = [];
    for (const s of scripts) {
        try {
            const data = JSON.parse(s.textContent);
            if (data['@type'] === 'ItemList' && data.itemListElement) {
                for (const item of data.itemListElement) {
                    if (item.item) results.push(item.item);
                    else results.push(item);
                }
            } else if (data['@type'] === 'Product') {
                results.push(data);
            } else if (Array.isArray(data)) {
                for (const d of data) {
                    if (d['@type'] === 'Product') results.push(d);
                }
            }
        } catch(e) {}
    }
    return results;
})())
"""


async def get_products():
    import nodriver as uc

    products = []
    seen_ids = set()

    browser_args = [
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-setuid-sandbox",
    ]
    if PROXY_ADDR and PROXY_ADDR != "none":
        browser_args.append(f"--proxy-server=http://{PROXY_ADDR}")

    try:
        browser = await uc.start(headless=False, sandbox=False, browser_args=browser_args)
    except Exception as e:
        log.error(f"[mediaexpert] Failed to start browser: {e}")
        return []

    try:
        for search_url in SEARCH_URLS:
            page = await browser.get(search_url)
            await asyncio.sleep(12)

            # Check CF
            title = await page.evaluate("document.title")
            if not title or "moment" in title.lower() or "checking" in title.lower():
                log.warning("[mediaexpert] CF challenge, waiting...")
                await asyncio.sleep(15)
                title = await page.evaluate("document.title")
                if not title or "moment" in title.lower():
                    log.error("[mediaexpert] CF block on %s", search_url)
                    continue

            # Dismiss cookies
            await page.evaluate("""
                (() => {
                    const bb = document.querySelectorAll('button');
                    for (const b of bb) {
                        const t = (b.textContent || '').toLowerCase();
                        if ((t.includes('akceptuj') || t.includes('zgadzam') || t.includes('accept'))
                            && b.offsetParent !== null) {
                            b.click(); return;
                        }
                    }
                })()
            """)
            await asyncio.sleep(2)

            for pg in range(1, MAX_PAGES + 1):
                if pg > 1:
                    # Try pagination
                    next_url = search_url + f"?page={pg}"
                    page = await browser.get(next_url)
                    await asyncio.sleep(8)
                    # Verify page loaded
                    title = await page.evaluate("document.title")
                    if not title or "moment" in title.lower():
                        await asyncio.sleep(10)

                # Try JSON-LD first (most reliable)
                jsonld_raw = await page.evaluate(JSONLD_EXTRACT_JS)
                jsonld_items = []
                if jsonld_raw:
                    try:
                        jsonld_items = json.loads(jsonld_raw)
                    except (json.JSONDecodeError, TypeError):
                        pass

                if jsonld_items:
                    for item in jsonld_items:
                        name = item.get("name", "")
                        if not name:
                            continue
                        # Extract PID from URL
                        item_url = item.get("url", "")
                        pid = ""
                        if item_url:
                            pid_match = re.search(r'-(\d+)\.html', item_url) or re.search(r'/(\d+)$', item_url)
                            if pid_match:
                                pid = pid_match.group(1)
                        if not pid:
                            pid = re.sub(r'[^a-z0-9]', '', name.lower())[:20]

                        if pid in seen_ids:
                            continue

                        # Apply filters
                        name_lower = name.lower()
                        if any(kw in name_lower for kw in EXCLUDE_KW):
                            continue
                        if not any(kw in name_lower for kw in INCLUDE_KW):
                            continue

                        seen_ids.add(pid)

                        # Price from offers
                        price_val = ""
                        offers = item.get("offers", {})
                        if isinstance(offers, dict):
                            price_val = str(offers.get("price", ""))
                        elif isinstance(offers, list) and offers:
                            price_val = str(offers[0].get("price", ""))

                        # Availability
                        avail = True
                        if isinstance(offers, dict):
                            avail_str = offers.get("availability", "")
                            if "OutOfStock" in str(avail_str):
                                avail = False

                        price_str = f"{price_val} zl" if price_val else "brak"
                        if item_url and not item_url.startswith("http"):
                            item_url = "https://www.mediaexpert.pl" + item_url

                        products.append({
                            "id": f"mediaexpert_{pid}",
                            "name": name,
                            "price": price_str,
                            "shop": "mediaexpert",
                            "url": item_url,
                            "image": item.get("image", ""),
                            "stock": 1 if avail else 0,
                            "available": avail,
                        })

                # Also try DOM extraction
                raw = await page.evaluate(EXTRACT_JS)
                if raw:
                    try:
                        items = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        items = []

                    for item in items:
                        pid = item.get("pid", "")
                        name = item.get("name", "")
                        if not name:
                            continue

                        # Skip marketplace products - only Media Expert own
                        if item.get("isMarketplace"):
                            continue

                        if not pid:
                            pid = re.sub(r'[^a-z0-9]', '', name.lower())[:20]

                        if pid in seen_ids:
                            continue

                        # Apply filters
                        name_lower = name.lower()
                        if any(kw in name_lower for kw in EXCLUDE_KW):
                            continue
                        if not any(kw in name_lower for kw in INCLUDE_KW):
                            continue

                        seen_ids.add(pid)

                        price_raw = item.get("price", "")
                        price_str = _format_price(price_raw) if price_raw else "brak"

                        item_url = item.get("url", "")
                        if item_url and not item_url.startswith("http"):
                            item_url = "https://www.mediaexpert.pl" + item_url

                        products.append({
                            "id": f"mediaexpert_{pid}",
                            "name": name,
                            "price": price_str,
                            "shop": "mediaexpert",
                            "url": item_url,
                            "image": item.get("image", ""),
                            "stock": 1 if item.get("available", True) else 0,
                            "available": item.get("available", True),
                        })

                # Check if there are more pages
                has_next = await page.evaluate("""
                    (() => {
                        const links = document.querySelectorAll('a[class*="next"], a[rel="next"], [class*="pagination"] a');
                        for (const l of links) {
                            const t = (l.textContent || '').toLowerCase();
                            if (t.includes('następna') || t.includes('next') || t === '›' || t === '»') {
                                return true;
                            }
                        }
                        return false;
                    })()
                """)
                if not has_next:
                    break

    except Exception as e:
        log.error(f"[mediaexpert] Error: {e}")
    finally:
        try:
            browser.stop()
        except:
            pass

    log.info(f"[MEDIAEXPERT] {len(products)} produktow")
    return products


def _format_price(price_raw):
    """Format price string."""
    if not price_raw:
        return "brak"
    try:
        price_str = str(price_raw).replace(",", ".").replace("\xa0", " ").strip()
        for suffix in ["zł", "PLN", "pln", "zl", "złotych"]:
            price_str = price_str.replace(suffix, "").strip()
        # Remove spaces between digits (e.g. "149 99" -> "149.99")
        price_str = re.sub(r'(\d+)\s+(\d{2})$', r'\1.\2', price_str)
        price_float = float(price_str)
        return f"{price_float:.2f} zl"
    except (ValueError, TypeError):
        return str(price_raw).strip()
