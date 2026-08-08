import asyncio
import aiohttp
from datetime import datetime
from collections import deque
from config import DISCORD_WEBHOOK, DISCORD_MAX_PER_MINUTE


class DiscordSender:
    def __init__(self):
        self.timestamps = deque()
        self.lock = asyncio.Lock()
        self.session = None

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _wait_rate_limit(self):
        while True:
            async with self.lock:
                now = asyncio.get_event_loop().time()
                while self.timestamps and now - self.timestamps[0] > 60:
                    self.timestamps.popleft()
                if len(self.timestamps) < DISCORD_MAX_PER_MINUTE:
                    self.timestamps.append(now)
                    return
                wait = 60 - (now - self.timestamps[0]) + 0.1
            await asyncio.sleep(wait)

    async def send(self, event_type: str, product: dict):
        if not DISCORD_WEBHOOK:
            return
        await self._wait_rate_limit()
        title_map = {
            "NEW_PRODUCT": "\U0001f195 NOWY PRODUKT",
            "RESTOCK": "\U0001f504 RESTOCK",
            "SOLD_OUT": "\u274c WYPRZEDANE",
            "PRICE_CHANGE": "\U0001f4b0 ZMIANA CENY",
            "SNAPSHOT": "\U0001f4e6 SNAPSHOT",
        }
        title = title_map.get(event_type, event_type)
        color_map = {
            "NEW_PRODUCT": 16777215,
            "RESTOCK": 65280,
            "SOLD_OUT": 16711680,
            "PRICE_CHANGE": 16753920,
            "SNAPSHOT": 5814783,
        }
        color = color_map.get(event_type, 5814783)
        # Override color based on availability for SNAPSHOT/NEW_PRODUCT
        if event_type in ("SNAPSHOT", "NEW_PRODUCT"):
            if product.get("available"):
                color = 65280  # green
            else:
                color = 16711680  # red
        name = product.get("name", "?")
        shop = product.get("shop", "?")
        price = product.get("price", "?")
        url = product.get("url", "")
        image = product.get("image", "")
        if event_type == "PRICE_CHANGE" and product.get("price_change"):
            price = product["price_change"]
        stock = product.get("stock")
        available = product.get("available", False)
        if isinstance(stock, (int, float)) and stock > 0:
            stock_text = f"\U0001f7e2 {int(stock)} szt."
        elif isinstance(stock, str) and stock:
            stock_text = f"\U0001f7e2 {stock}"
        elif available:
            stock_text = "\U0001f7e2 Dostepny"
        else:
            stock_text = "\U0001f534 Niedostepny"
        desc = (
            f"\U0001f4e6 **{name}**\n"
            f"\U0001f4b0 {price} | \U0001f3ea {shop}\n\n"
            f"\U0001f517 {url}\n\n"
            f"\U0001f552 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )
        embed = {
            "title": title,
            "description": desc,
            "color": color,
            "fields": [
                {"name": "\U0001f3ea Sklep", "value": shop, "inline": True},
                {"name": "\U0001f4b0 Cena", "value": str(price), "inline": True},
                {"name": "\U0001f4e6 Stan", "value": stock_text, "inline": True},
            ]
        }
        if image and image.startswith("http"):
            embed["image"] = {"url": image}
        session = await self._get_session()
        try:
            async with session.post(
                DISCORD_WEBHOOK,
                json={"embeds": [embed]},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status == 429:
                    data = await r.json()
                    retry_after = data.get("retry_after", 2)
                    await asyncio.sleep(retry_after)
                    async with session.post(
                        DISCORD_WEBHOOK,
                        json={"embeds": [embed]},
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as r2:
                        pass
        except Exception as e:
            print(f"[DISCORD ERROR] {e}")

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()


discord = DiscordSender()
