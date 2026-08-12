"""
Smart Proxy Router — provides best proxy per account/shop.

Usage:
    from proxy_router import get_playwright_proxy, get_proxy, request_ip_rotation, invalidate_proxy

    # In bot:
    proxy = get_playwright_proxy('tcgumisia', 'esemento@gmail.com')
    browser = await p.chromium.launch(proxy=proxy)  # proxy=None means direct

    # When request fails through a proxy:
    invalidate_proxy('mobile_tunnel')

    # When IP is banned:
    request_ip_rotation()
"""
import subprocess
import time
import logging
from typing import Optional, Dict, Tuple

log = logging.getLogger("proxy_router")

# === PROXY POOL ===
PROXIES = {
    "mobile_tunnel": {
        "url": "http://127.0.0.1:8888",
        "type": "http",
        "residential": True,
        "description": "Mobile IP via SSH tunnel (tinyproxy)",
    },
    "mobile_tailscale": {
        "url": "http://100.127.72.24:8888",
        "type": "http",
        "residential": True,
        "description": "Mobile IP via Tailscale direct",
    },
    "mobile_socks": {
        "url": "socks5://127.0.0.1:1080",
        "type": "socks5",
        "residential": True,
        "description": "Mobile IP via SOCKS5 (SSH dynamic)",
    },
    "direct": {
        "url": None,
        "type": "direct",
        "residential": False,
        "description": "VPS direct (146.59.45.228)",
    },
}

# === PER-ACCOUNT PROXY PREFERENCE ===
# Spread accounts across paths to avoid same-IP rate limiting
ACCOUNT_PROXY_MAP = {
    "esemento@gmail.com": ["mobile_tunnel", "mobile_tailscale", "direct"],
    "blackmat36@gmail.com": ["mobile_socks", "mobile_tunnel", "direct"],
    "tjbtaniojuzbylo@gmail.com": ["mobile_tailscale", "mobile_socks", "direct"],
    "y24015411@gmail.com": ["direct", "mobile_tunnel", "mobile_tailscale"],
}

# === SHOP REQUIREMENTS ===
# Shops that BLOCK datacenter IPs (need residential/mobile)
SHOP_REQUIRES_RESIDENTIAL = {
    "empik", "bonito", "proshop", "mediaexpert",
}

# Shops that need FlareSolverr (Cloudflare managed challenge)
SHOP_REQUIRES_FLARESOLVERR = {
    "battlestash", "tcg-zielona",
}

# === HEALTH CACHE ===
_health_cache: Dict[str, Tuple[bool, float]] = {}
HEALTH_TTL = 60  # seconds


def check_proxy_health(proxy_name: str) -> bool:
    """Check if proxy is working. Cached for HEALTH_TTL seconds."""
    now = time.time()
    cached = _health_cache.get(proxy_name)
    if cached and (now - cached[1]) < HEALTH_TTL:
        return cached[0]

    proxy_info = PROXIES.get(proxy_name)
    if not proxy_info:
        return False

    if proxy_info["type"] == "direct":
        _health_cache[proxy_name] = (True, now)
        return True

    proxy_url = proxy_info["url"]
    try:
        if proxy_info["type"] == "socks5":
            cmd = [
                "curl", "--socks5-hostname", proxy_url.replace("socks5://", ""),
                "-s", "-o", "/dev/null", "-w", "%{http_code}",
                "--connect-timeout", "4", "https://www.google.com",
            ]
        else:
            cmd = [
                "curl", "-x", proxy_url,
                "-s", "-o", "/dev/null", "-w", "%{http_code}",
                "--connect-timeout", "4", "https://www.google.com",
            ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7)
        healthy = result.stdout.strip() in ("200", "301", "302")
    except Exception:
        healthy = False

    _health_cache[proxy_name] = (healthy, now)
    return healthy


def get_proxy(shop: str = "", account_email: str = "") -> Dict:
    """
    Get best proxy for shop + account combination.
    Returns: {"server": url_or_None, "type": str, "name": str}
    """
    # FlareSolverr shops
    if shop in SHOP_REQUIRES_FLARESOLVERR:
        return {
            "server": "http://localhost:8191",
            "type": "flaresolverr",
            "name": "flaresolverr",
        }

    # Get preferred order for this account
    preferred = ACCOUNT_PROXY_MAP.get(account_email, ["mobile_tunnel", "direct"])

    # Filter for residential if shop requires it
    if shop in SHOP_REQUIRES_RESIDENTIAL:
        preferred = [p for p in preferred if PROXIES.get(p, {}).get("residential", False)]
        if not preferred:
            preferred = [k for k, v in PROXIES.items() if v.get("residential")]

    # Find first healthy proxy
    for proxy_name in preferred:
        if check_proxy_health(proxy_name):
            return {
                "server": PROXIES[proxy_name]["url"],
                "type": PROXIES[proxy_name]["type"],
                "name": proxy_name,
            }

    # All preferred dead — try ANY
    for proxy_name, proxy_info in PROXIES.items():
        if proxy_name not in preferred and check_proxy_health(proxy_name):
            return {
                "server": proxy_info["url"],
                "type": proxy_info["type"],
                "name": proxy_name,
            }

    # Everything dead — direct as last resort
    log.warning(f"ALL PROXIES DEAD for {shop}/{account_email} — using direct")
    return {"server": None, "type": "direct", "name": "direct_emergency"}


def get_playwright_proxy(shop: str = "", account_email: str = "") -> Optional[Dict]:
    """
    Get proxy in Playwright format. Returns None for direct (no proxy).
    Usage: browser = await p.chromium.launch(proxy=get_playwright_proxy(...))
    """
    proxy = get_proxy(shop, account_email)
    if not proxy or proxy["type"] in ("direct", "flaresolverr") or proxy["server"] is None:
        return None
    return {"server": proxy["server"]}


def invalidate_proxy(proxy_name: str):
    """Mark proxy as dead (call when request fails)."""
    _health_cache[proxy_name] = (False, time.time())
    log.warning(f"Proxy {proxy_name} INVALIDATED")


def request_ip_rotation():
    """Trigger IP rotation on mobile phone (async, non-blocking)."""
    try:
        subprocess.Popen(
            ["/opt/pokemon-monitor-v2/rotate_mobile_ip.sh"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Invalidate all mobile proxies during rotation
        for name in ["mobile_tunnel", "mobile_tailscale", "mobile_socks"]:
            _health_cache[name] = (False, time.time())
        log.info("IP rotation triggered")
    except Exception as e:
        log.error(f"IP rotation trigger failed: {e}")


# === CLI TEST ===
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=== PROXY ROUTER STATUS ===\n")
    for name in PROXIES:
        h = check_proxy_health(name)
        print(f"  {'✅' if h else '❌'} {name}: {PROXIES[name]['url'] or 'DIRECT'}")
    print("\n=== PER-ACCOUNT ROUTING ===\n")
    for email in ACCOUNT_PROXY_MAP:
        p = get_proxy("tcgumisia", email)
        print(f"  {email.split('@')[0]:25s} → {p['name']}")
    print("\n=== SHOP-SPECIFIC ===\n")
    for shop in ["empik", "battlestash", "tcgumisia", "bonito", "japancollectibles"]:
        p = get_proxy(shop, "esemento@gmail.com")
        print(f"  {shop:20s} → {p['name']} ({p['type']})")
