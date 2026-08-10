import logging
from discord_sender import discord
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
                    discord.send_nowait("SNAPSHOT", product)
                elif snapshot_done or len(old_by_id) > 0:
                    if product.get("available", False):
                        discord.send_nowait("NEW_PRODUCT", product)
                        check_smyk_autobuy(shop_name, "NEW_PRODUCT", product)
                        check_kartexpol_trigger("NEW_PRODUCT", product)
                        check_tantis_trigger("NEW_PRODUCT", product)
                        check_empik_trigger("NEW_PRODUCT", product)
                        check_strefatcg_trigger("NEW_PRODUCT", product)
                        check_japancollectibles_trigger("NEW_PRODUCT", product)
                        check_jc_30th_trigger("NEW_PRODUCT", product)
                        check_tcgumisia_trigger("NEW_PRODUCT", product)
                        check_mediaexpert_trigger("NEW_PRODUCT", product)
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
        except Exception as e:
            logger.error(f"[DETECT] Blad {shop_name}/{pid}: {e}")
            continue

    flush_kartexpol_batch()
    flush_tantis_batch()
    flush_jc_30th_batch()
    flush_tcgumisia_batch()
    flush_strefatcg_batch()
    return is_first
