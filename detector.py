import logging
from discord_sender import discord
from database import log_event, log_price_change, record_restock, activate_turbo_mode
from smyk_trigger import check_smyk_autobuy
from kartexpol_trigger import check_kartexpol_trigger, flush_kartexpol_batch
from tantis_trigger import check_tantis_trigger, flush_tantis_batch
from empik_trigger import check_empik_trigger
from strefatcg_trigger import check_strefatcg_trigger, flush_strefatcg_batch
from japancollectibles_trigger import check_japancollectibles_trigger
from japancollectibles_30th_trigger import check_jc_30th_trigger, flush_jc_30th_batch
from tcgumisia_trigger import check_tcgumisia_trigger, flush_tcgumisia_batch
from mediaexpert_trigger import check_mediaexpert_trigger

logger = logging.getLogger("monitor")

# === CROSS-SHOP CORRELATION ===
# When a restock/new product hits one of these shops, activate turbo mode on correlated shops
CORRELATED_SHOPS = {
    "tcgumisia.pl": ["kartexpol", "strefatcg", "japancollectibles", "boosterland"],
    "kartexpol": ["tcgumisia.pl", "strefatcg", "japancollectibles"],
    "strefatcg": ["tcgumisia.pl", "kartexpol", "japancollectibles"],
    "japancollectibles": ["tcgumisia.pl", "kartexpol", "strefatcg"],
    "boosterland": ["tcgumisia.pl", "kartexpol"],
}

# Turbo mode duration (minutes) when correlated shop has activity
TURBO_DURATION_MIN = 10


async def detect_and_send(shop_name, old_products, new_products, snapshot_done):
    old_by_id = {str(k): v for k, v in old_products.items()}
    is_first = len(old_products) == 0 and not snapshot_done

    restock_detected = False

    for product in new_products:
        pid = str(product.get("id", ""))
        if not pid:
            continue
        try:
            if pid not in old_by_id:
                if is_first and product.get("available", False):
                    discord.send_nowait("SNAPSHOT", product)
                    await log_event(shop_name, "SNAPSHOT", pid, product.get("name"),
                                    product.get("price"), product.get("url"))
                elif snapshot_done or len(old_by_id) > 0:
                    if product.get("available", False):
                        discord.send_nowait("NEW_PRODUCT", product)
                        await log_event(shop_name, "NEW_PRODUCT", pid, product.get("name"),
                                        product.get("price"), product.get("url"))
                        check_smyk_autobuy(shop_name, "NEW_PRODUCT", product)
                        check_kartexpol_trigger("NEW_PRODUCT", product)
                        check_tantis_trigger("NEW_PRODUCT", product)
                        check_empik_trigger("NEW_PRODUCT", product)
                        check_strefatcg_trigger("NEW_PRODUCT", product)
                        check_japancollectibles_trigger("NEW_PRODUCT", product)
                        check_jc_30th_trigger("NEW_PRODUCT", product)
                        check_tcgumisia_trigger("NEW_PRODUCT", product)
                        check_mediaexpert_trigger("NEW_PRODUCT", product)
                        restock_detected = True
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
                    discord.send_nowait("PRICE_CHANGE", product)
                    await log_event(shop_name, "PRICE_CHANGE", pid, product.get("name"),
                                    new_price, product.get("url"),
                                    {"old_price": old_price, "new_price": new_price})
                    await log_price_change(shop_name, pid, product.get("name", ""),
                                           old_price, new_price)
                    check_smyk_autobuy(shop_name, "PRICE_CHANGE", product)
                    check_kartexpol_trigger("PRICE_CHANGE", product)
                    check_tantis_trigger("PRICE_CHANGE", product)
                    check_empik_trigger("PRICE_CHANGE", product)
                    check_strefatcg_trigger("PRICE_CHANGE", product)
                    check_japancollectibles_trigger("PRICE_CHANGE", product)
                    check_jc_30th_trigger("PRICE_CHANGE", product)
                    check_tcgumisia_trigger("PRICE_CHANGE", product)
                    check_mediaexpert_trigger("PRICE_CHANGE", product)

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
                discord.send_nowait("RESTOCK", product)
                await log_event(shop_name, "RESTOCK", pid, product.get("name"),
                                product.get("price"), product.get("url"),
                                {"old_stock": str(old_stock), "new_stock": str(new_stock)})
                await record_restock(shop_name)
                restock_detected = True
                check_smyk_autobuy(shop_name, "RESTOCK", product)
                check_kartexpol_trigger("RESTOCK", product)
                check_tantis_trigger("RESTOCK", product)
                check_empik_trigger("RESTOCK", product)
                check_strefatcg_trigger("RESTOCK", product)
                check_japancollectibles_trigger("RESTOCK", product)
                check_jc_30th_trigger("RESTOCK", product)
                check_tcgumisia_trigger("RESTOCK", product)
                check_mediaexpert_trigger("RESTOCK", product)
            elif sold_out:
                new_p = str(product.get("price", "")).strip().lower()
                if new_p not in ("brak", "none", ""):
                    discord.send_nowait("SOLD_OUT", product)
                    await log_event(shop_name, "SOLD_OUT", pid, product.get("name"),
                                    product.get("price"), product.get("url"))
        except Exception as e:
            logger.error(f"[DETECT] Blad {shop_name}/{pid}: {e}")
            continue

    # === CROSS-SHOP INTELLIGENCE ===
    # If restock/new product detected, activate turbo mode on correlated shops
    if restock_detected:
        shop_field = new_products[0].get("shop", shop_name) if new_products else shop_name
        correlated = CORRELATED_SHOPS.get(shop_field, [])
        for corr_shop in correlated:
            try:
                await activate_turbo_mode(corr_shop, TURBO_DURATION_MIN)
                logger.info(f"[INTEL] Turbo mode activated for {corr_shop} (triggered by {shop_field})")
            except Exception:
                pass

    flush_kartexpol_batch()
    flush_tantis_batch()
    flush_jc_30th_batch()
    flush_tcgumisia_batch()
    flush_strefatcg_batch()
    return is_first
