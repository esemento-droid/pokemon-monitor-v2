#!/usr/bin/env python3
"""Full xjoy diagnostic — one shot, all info."""
import asyncio
import sys
sys.path.insert(0, "/opt/pokemon-monitor-v2")

from cf_solver import solve
from bs4 import BeautifulSoup


async def main():
    print("=" * 60)
    print("XJOY.PL — FULL DIAGNOSTIC")
    print("=" * 60)

    html = await solve("https://www.xjoy.pl/278-pokemon-tcg", timeout=70)
    if not html:
        print("❌ SOLVE FAILED — CF not passed")
        return

    print(f"\n✅ CF passed. HTML: {len(html)} chars")

    # Check if it's actually challenge page
    h = html.lower()
    if "weryfikac" in h and len(html) < 30000:
        print("❌ STILL CHALLENGE PAGE")
        return

    soup = BeautifulSoup(html, "lxml")

    # 1. Find ALL product-related classes
    print("\n--- 1. PRODUCT CSS CLASSES ---")
    all_classes = set()
    for el in soup.select("[class]"):
        for c in el.get("class", []):
            if any(x in c.lower() for x in ["product", "item", "listing", "catalog"]):
                all_classes.add(c)
    for c in sorted(all_classes):
        print(f"  .{c}")

    # 2. Find listing container
    print("\n--- 2. LISTING CONTAINERS ---")
    for sel in ["#js-product-list", ".products", "#product_list", ".product_list",
                "#js-product-list-top", ".product-listing", "#category-products"]:
        found = soup.select(sel)
        if found:
            print(f"  {sel}: {len(found)} found")

    # 3. Dump the FIRST product card (whatever structure)
    print("\n--- 3. PRODUCT CARD STRUCTURE ---")
    # Try multiple PrestaShop selectors
    selectors = [
        "article.product-miniature",
        ".product-miniature",
        ".product_item",
        ".product-container",
        ".item-product",
        ".js-product-miniature",
        "[data-id-product-attribute]",
        ".product-layout",
        ".product-box",
    ]
    items = []
    used_selector = None
    for sel in selectors:
        items = soup.select(sel)
        if items:
            used_selector = sel
            break

    if not items:
        # Broader: find parent of add-to-cart buttons
        atc_buttons = soup.select("a[data-id-product]")
        if atc_buttons:
            # Go up to find product card wrapper
            parent = atc_buttons[0].parent
            for _ in range(5):
                if parent and parent.name in ("article", "div", "li"):
                    siblings = parent.parent.find_all(parent.name, recursive=False)
                    if len(siblings) > 3:
                        items = siblings
                        used_selector = f"parent-walk: {parent.name}.{parent.get('class','')}"
                        break
                parent = parent.parent if parent else None

    if items:
        print(f"  Selector: {used_selector}")
        print(f"  Total items: {len(items)}")
        print(f"\n  --- RAW HTML of item #1 (first 2000 chars): ---")
        print(str(items[0])[:2000])
        print(f"\n  --- RAW HTML of item #2 (first 1500 chars): ---")
        if len(items) > 1:
            print(str(items[1])[:1500])
    else:
        print("  ❌ NO PRODUCT CARDS FOUND with any selector!")
        print("\n  Dumping body text (first 1000 chars):")
        print(soup.get_text(" ", strip=True)[:1000])

    # 4. Pagination
    print("\n--- 4. PAGINATION ---")
    page_links = soup.select(".pagination a, a[rel=next], .page-link, .pages a")
    print(f"  Page links found: {len(page_links)}")
    for pl in page_links[:8]:
        print(f"  {pl.get_text(strip=True)[:10]} -> {pl.get('href','')[-50:]}")

    # 5. Total product count (if shown)
    print("\n--- 5. TOTAL COUNT ---")
    count_el = soup.select_one(".total-products, .product-count, .showing, .pagination-summary")
    if count_el:
        print(f"  {count_el.get_text(strip=True)}")
    else:
        print("  (not found)")

    # 6. Quick product list (names + prices from whatever we found)
    print("\n--- 6. PARSED PRODUCTS ---")
    if items:
        for i, item in enumerate(items[:30]):
            # Try to extract name
            name_el = (item.select_one(".product-title a") or
                       item.select_one("h2 a, h3 a, h4 a") or
                       item.select_one("a.product-name, a.product_name") or
                       item.select_one("a[title]"))
            name = name_el.get_text(strip=True) if name_el else ""
            url = name_el.get("href", "") if name_el else ""

            # Try to extract price
            price_el = (item.select_one(".product-price, .price, [itemprop=price]") or
                        item.select_one(".regular-price, .current-price"))
            price = price_el.get_text(strip=True) if price_el else "?"

            # Availability
            avail_el = item.select_one(".product-availability, .availability, .stock")
            avail = avail_el.get_text(strip=True) if avail_el else "?"

            print(f"  {i+1:2}. {name[:55]:55} | {price:12} | {avail[:20]}")

    print("\n" + "=" * 60)
    print("END DIAGNOSTIC")


asyncio.run(main())
