#!/usr/bin/env python3
"""Debug: show checkout page structure (radios, checkboxes, buttons)"""
import asyncio
from patchright.async_api import async_playwright

BASE_URL = "https://www.kartexpol.pl"

async def check():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--no-sandbox","--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
        page = await ctx.new_page()

        # Login
        await page.goto(f"{BASE_URL}/pl/login", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        await page.evaluate("""
            document.querySelectorAll('.consents, .consents__mask, [class*=consent], .cookie-bar').forEach(el => el.remove());
            document.body.style.pointerEvents = 'auto';
        """)
        await page.evaluate("""() => {
            const m = document.querySelector('input[name="email"]');
            const p = document.querySelector('input[name="password"]');
            if (m) { m.focus(); m.value = 't11008543@gmail.com'; m.dispatchEvent(new Event('input',{bubbles:true})); }
            if (p) { p.focus(); p.value = 'mt!cSsphud4Zhnz'; p.dispatchEvent(new Event('input',{bubbles:true})); }
        }""")
        await asyncio.sleep(1)
        await page.evaluate("""() => { const btn = Array.from(document.querySelectorAll('button[type="submit"]')).find(b => b.innerText.includes('Zaloguj')); if (btn) btn.click(); }""")
        await asyncio.sleep(5)
        print(f"LOGGED IN: {'wyloguj' in (await page.content()).lower()}")

        # ATC
        await page.goto("https://www.kartexpol.pl/pl/p/Booster-Pokemon-Nihil-Zero/179", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        await page.evaluate("""() => { const btn = document.querySelector('.addtobasket'); if (btn) btn.click(); }""")
        await asyncio.sleep(3)

        # Go to checkout
        await page.goto(f"{BASE_URL}/pl/basket", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        await page.evaluate("""() => {
            document.querySelectorAll('.consents, .consents__mask, [class*=consent], .cookie-bar').forEach(el => el.remove());
            document.body.style.pointerEvents = 'auto';
        }""")
        await page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('a, button'));
            const btn = btns.find(b => b.innerText.includes('Dostawa i płatność') || b.innerText.includes('ZAMAWIAM'));
            if (btn) btn.click();
        }""")
        await asyncio.sleep(6)
        print(f"CHECKOUT URL: {page.url}")

        # Inspect all radios
        radios = await page.evaluate("""() => {
            const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
            return radios.map(r => ({
                name: r.name, 
                id: r.id, 
                value: r.value, 
                checked: r.checked,
                labelText: (r.closest('label') || r.parentElement)?.innerText?.substring(0,60) || ''
            }));
        }""")
        print(f"RADIOS ({len(radios)}):")
        for r in radios:
            print(f"  [{('X' if r['checked'] else ' ')}] name={r['name']} value={r['value']} label={r['labelText'][:50]}")

        # Inspect checkboxes
        checks = await page.evaluate("""() => {
            const cbs = Array.from(document.querySelectorAll('input[type="checkbox"]'));
            return cbs.map(c => ({
                name: c.name,
                id: c.id,
                checked: c.checked,
                labelText: (c.closest('label') || document.querySelector('label[for="'+c.id+'"]') || c.parentElement)?.innerText?.substring(0,60) || ''
            }));
        }""")
        print(f"CHECKBOXES ({len(checks)}):")
        for c in checks:
            print(f"  [{('X' if c['checked'] else ' ')}] name={c['name']} id={c['id']} label={c['labelText'][:50]}")

        # Inspect submit buttons
        btns = await page.evaluate("""() => {
            const all = Array.from(document.querySelectorAll('button, input[type="submit"], a.btn'));
            return all.filter(b => b.offsetParent !== null).map(b => ({
                tag: b.tagName, text: (b.innerText||b.value||'').substring(0,40), cls: b.className.substring(0,40), disabled: b.disabled
            }));
        }""")
        print(f"BUTTONS ({len(btns)}):")
        for b in btns:
            print(f"  {b['tag']} text='{b['text']}' cls={b['cls']} disabled={b['disabled']}")

        await browser.close()

asyncio.run(check())
