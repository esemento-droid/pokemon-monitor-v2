#!/usr/bin/env python3
"""Debug kartexpol login - click Zaloguj button instead of form.submit()"""
import asyncio
from patchright.async_api import async_playwright

async def check():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--no-sandbox","--disable-blink-features=AutomationControlled"])
        page = await browser.new_page()
        await page.goto("https://www.kartexpol.pl/pl/login", wait_until="domcontentloaded")
        await asyncio.sleep(4)

        # Dismiss consent
        try:
            consent = page.locator('.consents__btn')
            if await consent.count() > 0:
                await consent.first.click(timeout=3000)
                await asyncio.sleep(1)
        except:
            pass
        await page.evaluate("""
            document.querySelectorAll('.consents, .consents__mask, [class*=consent], .cookie-bar').forEach(el => el.remove());
            document.body.style.pointerEvents = 'auto';
        """)
        await asyncio.sleep(1)

        # Fill form via JS with input events
        email = "t11008543@gmail.com"
        password = "mt!cSsphud4Zhnz"
        
        await page.evaluate(f"""() => {{
            const mailEl = document.querySelector('input[name="email"]');
            const passEl = document.querySelector('input[name="password"]');
            if (mailEl) {{
                mailEl.focus();
                mailEl.value = '{email}';
                mailEl.dispatchEvent(new Event('input', {{bubbles:true}}));
                mailEl.dispatchEvent(new Event('change', {{bubbles:true}}));
            }}
            if (passEl) {{
                passEl.focus();
                passEl.value = '{password}';
                passEl.dispatchEvent(new Event('input', {{bubbles:true}}));
                passEl.dispatchEvent(new Event('change', {{bubbles:true}}));
            }}
        }}""")
        await asyncio.sleep(1)
        
        vals = await page.evaluate("""() => {
            const m = document.querySelector('input[name="email"]');
            const p = document.querySelector('input[name="password"]');
            return JSON.stringify({emailVal: m?.value, passLen: p?.value?.length});
        }""")
        print(f"VALUES: {vals}")

        # Find and click the submit button (not form.submit)
        buttons = await page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button, input[type="submit"]'));
            return btns.map(b => ({text: b.innerText || b.value, type: b.type, className: b.className}));
        }""")
        print(f"BUTTONS: {buttons}")

        # Click "Zaloguj sie" button
        clicked = await page.evaluate("""() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Zaloguj'));
            if (btn) { btn.click(); return btn.innerText; }
            const submit = document.querySelector('form[action*="/pl/login"] button[type="submit"]');
            if (submit) { submit.click(); return 'submit:' + submit.innerText; }
            return 'NOT FOUND';
        }""")
        print(f"CLICKED: {clicked}")
        await asyncio.sleep(6)

        url = page.url
        content = await page.content()
        has_wyloguj = "wyloguj" in content.lower()
        body_text = await page.evaluate("() => document.body.innerText.substring(0, 400)")
        print(f"URL: {url}")
        print(f"LOGGED IN: {has_wyloguj}")
        print(f"BODY: {body_text[:300]}")
        
        await browser.close()

asyncio.run(check())
