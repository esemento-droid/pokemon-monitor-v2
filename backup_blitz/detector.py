import logging
from discord_sender import discord

logger = logging.getLogger("monitor")


async def detect_and_send(shop_name, old_products, new_products, snapshot_done):
    old_by_id = {str(k): v for k, v in old_products.items()}
    is_first = len(old_products) == 0 and not snapshot_done

    for product in new_products:
        pid = str(product.get("id", ""))
        if not pid:
            continue
        try:
            if pid not in old_by_id:
                if is_first and product.get("available", False):
                    await discord.send("SNAPSHOT", product)
                elif snapshot_done or len(old_by_id) > 0:
                    if product.get("available", False):
                        await discord.send("NEW_PRODUCT", product)
                continue

            old = old_by_id[pid]

            # Zmiana ceny
            old_price = str(old.get("price", "")).strip()
            new_price = str(product.get("price", "")).strip()
            if old_price and new_price and old_price != new_price and new_price.lower() != "brak":
                if old_price.strip() in ("1 PLN", "1 zl", "1.00 PLN"):
                    pass
                else:
                    product["price_change"] = f"{old_price} -> {new_price}"
                    await discord.send("PRICE_CHANGE", product)

            # Zmiana dostepnosci
            old_available = old.get("available", False)
            new_available = product.get("available", False)
            old_stock = old.get("stock")
            new_stock = product.get("stock")

            if isinstance(old_stock, (int, float)) and isinstance(new_stock, (int, float)):
                restock = old_stock <= 0 and new_stock > 0
                sold_out = old_stock > 0 and new_stock <= 0
            else:
                restock = not old_available and new_available
                sold_out = old_available and not new_available

            if restock:
                await discord.send("RESTOCK", product)
            elif sold_out:
                new_p = str(product.get("price", "")).strip().lower()
                if new_p not in ("brak", "none", ""):
                    await discord.send("SOLD_OUT", product)
        except Exception as e:
            logger.error(f"[DETECT] Blad {shop_name}/{pid}: {e}")
            continue

    return is_first
