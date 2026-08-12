import asyncio
import aiohttp
from datetime import datetime
from collections import deque
from config import DISCORD_WEBHOOK, DISCORD_MAX_PER_MINUTE
from price_compare import format_comparison


class DiscordSender:
    def __init__(self):
        self.timestamps = deque()
        self._queue = None
        self._task = None
        self.session = None

    def start(self):
        self._queue = asyncio.Queue(maxsize=500)
        self._task = asyncio.create_task(self._worker())

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _worker(self):
        while True:
            try:
                embed = await self._queue.get()
                await self._rate_limit()
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
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[DISCORD WORKER] {e}")
                await asyncio.sleep(1)


    async def _rate_limit(self):
        now = asyncio.get_event_loop().time()
        while self.timestamps and now - self.timestamps[0] > 60:
            self.timestamps.popleft()
        if len(self.timestamps) >= DISCORD_MAX_PER_MINUTE:
            wait = 60 - (now - self.timestamps[0]) + 0.1
            await asyncio.sleep(wait)
            now = asyncio.get_event_loop().time()
            while self.timestamps and now - self.timestamps[0] > 60:
                self.timestamps.popleft()
        self.timestamps.append(asyncio.get_event_loop().time())

    def send_nowait(self, event_type: str, product: dict):
        """Fire-and-forget. Never blocks the caller."""
        if not DISCORD_WEBHOOK:
            return
        if self._queue is None:
            return
        embed = self._build_embed(event_type, product)
        try:
            self._queue.put_nowait(embed)
        except asyncio.QueueFull:
            print("[DISCORD] Queue full, dropping message")

    async def send(self, event_type: str, product: dict):
        """Backwards compat - but now non-blocking via queue."""
        self.send_nowait(event_type, product)

    def _build_embed(self, event_type, product):
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
        if event_type in ("SNAPSHOT", "NEW_PRODUCT"):
            color = 65280 if product.get("available") else 16711680

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
        # Add price comparison field if available
        price_compare_data = product.get("price_compare")
        if price_compare_data:
            compare_text = format_comparison(price_compare_data)
            if compare_text:
                embed["fields"].append(
                    {"name": "\U0001f4ca Porównanie cen", "value": compare_text, "inline": False}
                )
        if image and image.startswith("http"):
            image = image.replace(" ", "%20")
            embed["image"] = {"url": image}
        return embed

    async def close(self):
        if self._queue and not self._queue.empty():
            for _ in range(60):
                if self._queue.empty():
                    break
                await asyncio.sleep(0.5)
        if self._task:
            self._task.cancel()
        if self.session and not self.session.closed:
            await self.session.close()


discord = DiscordSender()
