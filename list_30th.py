#!/usr/bin/env python3
"""List all 30th products on tcgumisia.pl with prices."""
import asyncio
from patchright.async_api import async_playwright

PROXY = "http://127.0.0.1:8888"

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=False, args=["--no-sandbox", f"--proxy-server={PROXY}"])
        page = await (await b.new_context()).new_page()

        all_products = []

        for cat in ["/pokemon", "/pre-order"]:
            await page.goto(f"https://tcgumisia.pl{cat}", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)
            products = await page.evaluate("""() => {
                const boxes = document.querySelectorAll(".c-product-box");
                const results = [];
                for (const box of boxes) {
                    const title = box.querySelector(".c-product-box__title");
                    const price = box.querySelector(".c-product-box__price-value");
                    const avail = box.querySelector(".c-avaibility");
                    const name = title ? title.textContent.trim() : "";
                    const nameL = name.toLowerCase();
                    if (nameL.includes("30th") || nameL.includes("30 celebration") || nameL.includes("30-lecie") || nameL.includes("30 lecie")) {
                        const availClass = avail ? avail.className : "";
                        results.push({
                            name,
                            price: price ? price.textContent.trim() : "brak",
                            available: !availClass.includes("--none"),
                            category: arguments[0] || "unknown"
                        });
                    }
                }
                return results;
            }""")
            for prod in products:
                prod["category"] = cat
                all_products.append(prod)

        print(f"=== TCGumisia 30th products ({len(all_products)} total) ===\n")
        for p2 in all_products:
            status = "IN STOCK" if p2["available"] else "SOLD OUT"
            print(f"[{status}] {p2['name']}")
            print(f"         Cena: {p2['price']} | Kategoria: {p2['category']}")
            print()

        if not all_products:
            print("BRAK produktow 30th!")

        await b.close()

asyncio.run(main())
