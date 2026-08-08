import asyncio
import sys
import os
import tempfile
import nodriver as uc

TURNSTILE_SITEKEY = "0x4AAAAAAAcP9JGdR8yyj58F"
TURNSTILE_SITEURL = "https://www.empik.com/"

async def solve_turnstile(sitekey=None, siteurl=None, timeout=60):
    sitekey = sitekey or TURNSTILE_SITEKEY
    siteurl = siteurl or TURNSTILE_SITEURL

    os.environ.setdefault("DISPLAY", ":99")

    html = f"""<!DOCTYPE html>
<html><head>
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit" async defer></script>
</head><body>
<div id="cf-widget"></div>
<input type="hidden" id="cf-token" value="">
<script>
function onToken(token) {{
    document.getElementById("cf-token").value = token;
    document.title = "SOLVED:" + token.substring(0, 20);
}}
window.onload = function() {{
    setTimeout(function() {{
        if (typeof turnstile !== "undefined") {{
            turnstile.render("#cf-widget", {{
                sitekey: "{sitekey}",
                callback: onToken
            }});
        }}
    }}, 1000);
}};
</script>
</body></html>"""

    # Write HTML to temp file
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, dir="/tmp")
    tmp.write(html)
    tmp.close()

    browser = await uc.start(
        browser_executable_path="/usr/bin/chromium",
        headless=False,
        browser_args=[
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--window-size=800,600",
        ],
    )
    try:
        page = await browser.get(f"file://{tmp.name}")
        await asyncio.sleep(4)

        # Try clicking the turnstile checkbox
        for attempt in range(8):
            try:
                title = await page.evaluate("document.title")
                if title and "SOLVED:" in str(title):
                    break
                # Find and click iframe
                iframes = await page.select_all("iframe")
                for iframe in iframes:
                    box = await iframe.get_position()
                    if box and box[2] > 0:
                        x = box[0] + 30
                        y = box[1] + 20
                        await page.mouse.click(x, y)
                        break
            except Exception as e:
                pass
            await asyncio.sleep(3)

        # Wait for token via title change
        elapsed = 0
        while elapsed < timeout:
            try:
                title = await page.evaluate("document.title")
                if title and "SOLVED:" in str(title):
                    # Get full token from input
                    token = await page.evaluate("document.getElementById('cf-token').value")
                    if token and len(str(token)) > 20:
                        return str(token)
            except Exception:
                pass
            await asyncio.sleep(1)
            elapsed += 1

        return None
    finally:
        try:
            browser.stop()
        except Exception:
            pass
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

if __name__ == "__main__":
    token = asyncio.run(solve_turnstile())
    if token:
        print(f"TOKEN_OK len={len(token)}")
        print(token[:80])
    else:
        print("TOKEN_FAIL")
