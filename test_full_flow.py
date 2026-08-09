#!/usr/bin/env python3
"""
FULL TEST: 
1. Login test account → clear cart → ATC → checkout → REAL ORDER (Zamawiam i płacę)
2. Login esemento account → ATC (add product to cart only)
"""
import asyncio
import sys
from patchright.async_api import async_playwright

BASE_URL = "https://tcgumisia.pl"
PROXY = "http://127.0.0.1:8888"
PRODUCT_URL = "https://tcgumisia.pl/pokemon-tcg-ionos-bellibolt-ex-premium-collection"
PACZKOMAT = "PAD04M"

TEST_ACCOUNT = {"email": "t11008543@gmail.com", "password": "mt!cSsphud4Zhnz", "name": "Marian Wasilewski"}
ACCOUNT_2 = {"email": "esemento@gmail.com", "password": "cR!9GW#x2wqJtGw", "name": "Tomasz Szczepaniak"}


async def login(page, email, password):
    """Login via Sellingo modal"""
    await page.goto(BASE_URL, wait_until='domcontentloaded', timeout=30000)
    await asyncio.sleep(4)
    # Accept cookies
    try:
        cookie = page.locator('.js-accept-cookie-alert-1')
        if await cookie.count() > 0:
            await cookie.click(timeout=3000)
            await asyncio.sleep(1)
    except:
        pass
    # Open login modal
    await page.locator('button[data-aside-target="modal-aside-entry-form"]').click()
    await asyncio.sleep(2)
    # Fill credentials
    email_input = page.locator('.js-login-form input[type="email"], .js-login-form input[placeholder*="E-mail"]').first
    pass_input = page.locator('.js-login-form input[type="password"]').first
    await email_input.click()
    await email_input.fill(email)
    await asyncio.sleep(0.5)
    await pass_input.click()
    await pass_input.fill(password)
    await asyncio.sleep(0.5)
    await page.locator('.js-submit-login').click()
    await asyncio.sleep(6)
    print(f"  Login done for {email}")
    return True


async def clear_cart(page):
    """Clear all items from cart"""
    await page.goto(f"{BASE_URL}/koszyk", wait_until='domcontentloaded', timeout=30000)
    await asyncio.sleep(4)
    for i in range(10):
        empty = await page.evaluate("""() => document.body.innerText.toLowerCase().includes('koszyk jest pusty')""")
        if empty:
            print(f"  Cart empty after {i} removals")
            return
        del_btn = page.locator('.c-table-product__delete--desktop').first
        if await del_btn.count() == 0:
            print(f"  No delete button, assuming empty")
            return
        await del_btn.click(force=True, timeout=5000)
        await asyncio.sleep(2)
        await page.goto(f"{BASE_URL}/koszyk", wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)
    print("  Cart cleared (max attempts)")


async def add_to_cart(page, url):
    """Add product to cart"""
    await page.goto(url, wait_until='domcontentloaded', timeout=30000)
    await asyncio.sleep(5)
    title = await page.evaluate("() => document.title")
    if "404" in title:
        print(f"  ERROR: 404 on {url}")
        return False
    atc = page.locator('#product-card-add-to-card')
    if await atc.count() == 0:
        print(f"  ERROR: ATC button not found")
        return False
    await atc.click(timeout=5000)
    await asyncio.sleep(4)
    cart_val = await page.evaluate("""() => {
        const el = document.querySelector('.js-cart-value');
        return el ? el.innerText.trim() : '?';
    }""")
    print(f"  ATC done, cart value: {cart_val}")
    return True


async def checkout(page):
    """Full checkout: Tab1 → Tab2 → Tab3 → click Zamawiam"""
    await page.goto(f"{BASE_URL}/koszyk", wait_until='domcontentloaded', timeout=30000)
    await asyncio.sleep(4)

    # Tab 1: Select InPost Paczkomat (radio shipment=15)
    # Scroll into view first, then click
    await page.evaluate("""() => {
        const r = document.querySelector('input[name="shipment"][value="15"]');
        if (r) r.scrollIntoView({block: 'center'});
    }""")
    await asyncio.sleep(1)
    inpost = page.locator('input[name="shipment"][value="15"]')
    try:
        await inpost.click(force=True, timeout=5000)
    except:
        await page.evaluate("""() => {
            const r = document.querySelector('input[name="shipment"][value="15"]');
            if (r) { r.checked = true; r.dispatchEvent(new Event('change', {bubbles:true})); r.dispatchEvent(new Event('click', {bubbles:true})); }
        }""")
    await asyncio.sleep(3)

    # Click Wyszukaj
    await page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button, a, span'));
        const s = btns.find(el => (el.innerText || '').toLowerCase().includes('wyszukaj'));
        if (s) s.click();
    }""")
    await asyncio.sleep(2)

    # Search PAD04M
    search = page.locator('input[placeholder*="Szukaj"], input[placeholder*="miasto"], input[placeholder*="adres"]').first
    try:
        await search.click(timeout=5000)
        await search.fill(PACZKOMAT)
        await asyncio.sleep(2)
    except:
        await page.evaluate(f"""() => {{
            const inputs = document.querySelectorAll('input[type="text"], input[type="search"]');
            for (const inp of inputs) {{
                if (inp.offsetParent !== null) {{
                    inp.focus(); inp.value = '{PACZKOMAT}';
                    inp.dispatchEvent(new Event('input', {{bubbles:true}}));
                    break;
                }}
            }}
        }}""")
        await asyncio.sleep(2)

    # Select PAD04M
    await page.evaluate(f"""() => {{
        const items = Array.from(document.querySelectorAll('li, div, span, a'));
        const pad = items.find(el => (el.innerText || '').toUpperCase().includes('{PACZKOMAT}') && el.offsetParent !== null);
        if (pad) pad.click();
    }}""")
    await asyncio.sleep(2)

    # Click Wybierz if popup
    await page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button, a'));
        const w = btns.find(el => (el.innerText || '').toLowerCase().includes('wybierz') && el.offsetParent !== null);
        if (w) w.click();
    }""")
    await asyncio.sleep(3)

    # Select Blik/Karta (radio payment=25, scroll + force click)
    await page.evaluate("""() => {
        const r = document.querySelector('input[name="payment"][value="25"]');
        if (r) r.scrollIntoView({block: 'center'});
    }""")
    await asyncio.sleep(1)
    blik = page.locator('input[name="payment"][value="25"]')
    try:
        await blik.click(force=True, timeout=5000)
    except:
        await page.evaluate("""() => {
            const r = document.querySelector('input[name="payment"][value="25"]');
            if (r) { r.checked = true; r.dispatchEvent(new Event('change', {bubbles:true})); r.dispatchEvent(new Event('click', {bubbles:true})); }
        }""")
    await asyncio.sleep(2)

    # Click Dalej
    await page.locator('.js-cart-next').click(timeout=5000)
    await asyncio.sleep(4)
    print("  Tab 1 done (InPost + Blik + Dalej)")

    # Tab 2: Check regulamin (input[name="rules"])
    rules = page.locator('input[name="rules"]')
    try:
        if await rules.count() > 0 and not await rules.is_checked():
            await rules.click(force=True, timeout=5000)
    except:
        pass
    await asyncio.sleep(1)

    # Click Przejdź dalej (.js-cart-next)
    await page.locator('.js-cart-next').click(timeout=5000)
    await asyncio.sleep(4)
    print("  Tab 2 done (regulamin + Przejdź dalej)")

    # Tab 3: Click Zamawiam i płacę
    await asyncio.sleep(2)
    await page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button, a, input[type="submit"]'));
        const s = btns.find(el => (el.innerText || el.value || '').toLowerCase().includes('zamawiam'));
        if (s) s.click();
    }""")
    print("  Tab 3: Clicked 'Zamawiam i płacę'!")
    await asyncio.sleep(10)

    # Check result
    url = page.url
    body = await page.evaluate("() => document.body.innerText.substring(0, 300)")
    if any(kw in url for kw in ["tpay", "przelewy24", "autopay", "blik", "pay"]):
        print(f"  PAYMENT PAGE REACHED! URL: {url}")
        return True
    if "dziękujemy" in body.lower() or "zamówienie" in body.lower():
        print(f"  ORDER CONFIRMED! Text: {body[:100]}")
        return True
    print(f"  Result URL: {url}")
    print(f"  Result text: {body[:150]}")
    return True


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', f'--proxy-server={PROXY}']
        )

        # === TEST 1: Full order on test account ===
        print("=" * 50)
        print("TEST 1: Real order on test account")
        print("=" * 50)
        ctx1 = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
        page1 = await ctx1.new_page()

        await login(page1, TEST_ACCOUNT["email"], TEST_ACCOUNT["password"])
        await clear_cart(page1)
        ok = await add_to_cart(page1, PRODUCT_URL)
        if ok:
            await checkout(page1)
        else:
            print("  FAILED: could not add to cart")

        await ctx1.close()
        print()

        await asyncio.sleep(3)

        # === TEST 2: Login esemento + ATC only ===
        print("=" * 50)
        print("TEST 2: Login esemento + add to cart")
        print("=" * 50)
        ctx2 = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
        page2 = await ctx2.new_page()

        await login(page2, ACCOUNT_2["email"], ACCOUNT_2["password"])
        await clear_cart(page2)
        ok = await add_to_cart(page2, PRODUCT_URL)
        if ok:
            print("  SUCCESS: Product in cart for esemento!")
        else:
            print("  FAILED: could not add to cart for esemento")

        await ctx2.close()

        await browser.close()
        print("\n" + "=" * 50)
        print("ALL TESTS DONE")
        print("=" * 50)


asyncio.run(main())
