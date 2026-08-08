#!/usr/bin/env python3
"""Debug kartexpol login - show what happens after form submit"""
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

        # Fill form
        email = "t11008543@gmail.com"
        password = "mt!cSsphud4Zhnz"
        
        # Check what selectors find
        found = await page.evaluate(f"""() => {{
            const mailEl = document.querySelector('input[name="email"]') || document.querySelector('#mail_input_long') || document.querySelector('input[name="mail"]');
            const passEl = document.querySelector('input[name="password"]') || document.querySelector('#pass_input_long') || document.querySelector('input[name="pass"]');
            const form = document.querySelector('form[action*="/pl/login"]');
            return JSON.stringify({{
                mailFound: !!mailEl, mailName: mailEl?.name, mailId: mailEl?.id,
                passFound: !!passEl, passName: passEl?.name, passId: passEl?.id,
                formFound: !!form, formAction: form?.action
            }});
        }}""")
        print(f"SELECTORS: {found}")

        # Fill via JS
        await page.evaluate(f"""
            const mailEl = document.querySelector('input[name="email"]') || document.querySelector('#mail_input_long') || document.querySelector('input[name="mail"]');
            const passEl = document.querySelector('input[name="password"]') || document.querySelector('#pass_input_long') || document.querySelector('input[name="pass"]');
            if (mailEl) {{ mailEl.value = '{email}'; mailEl.dispatchEvent(new Event('input', {{bubbles:true}})); }}
            if (passEl) {{ passEl.value = '{password}'; passEl.dispatchEvent(new Event('input', {{bubbles:true}})); }}
        """)
        await asyncio.sleep(1)
        
        # Verify values set
        vals = await page.evaluate("""() => {
            const m = document.querySelector('input[name="email"]');
            const p = document.querySelector('input[name="password"]');
            return JSON.stringify({emailVal: m?.value, passVal: p?.value?.length});
        }""")
        print(f"VALUES SET: {vals}")

        # Submit form
        await page.evaluate("""
            const form = document.querySelector('form[action*="/pl/login"]');
            if (form) form.submit();
        """)
        print("FORM SUBMITTED")
        await asyncio.sleep(6)

        # Check result
        url = page.url
        content = await page.content()
        has_wyloguj = "wyloguj" in content.lower()
        body_text = await page.evaluate("() => document.body.innerText.substring(0, 500)")
        print(f"URL AFTER: {url}")
        print(f"HAS WYLOGUJ: {has_wyloguj}")
        print(f"BODY: {body_text[:300]}")
        
        await browser.close()

asyncio.run(check())
