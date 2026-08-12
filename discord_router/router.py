import os
import asyncio
import subprocess
import json
from datetime import datetime
import discord
from dotenv import load_dotenv

from config import (
    SOURCE_CHANNEL_ID,
    CATEGORY_ID,
    GUILD_ID,
    MONITOR_CHANNEL_NAME,
    SYSTEM_CATEGORY_NAME,
    STATUS_CHANNEL_NAME,
    HEARTBEAT_CHANNEL_NAME,
    ERROR_CHANNEL_NAME,
    FOREIGN_SHOPS,
    FOREIGN_CATEGORY_NAME,
    LEGO_SHOPS,
    LEGO_CATEGORY_NAME
)

load_dotenv("/opt/discord-router/.env")

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

system_channels = {}
channel_locks = {}
channel_lock_master = asyncio.Lock()


def router_log(event, data=None):
    try:
        log = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event": event,
            "data": data or {}
        }

        with open(
            "/opt/discord-router/router.log",
            "a",
            encoding="utf-8"
        ) as f:
            f.write(
                json.dumps(
                    log,
                    ensure_ascii=False
                )
                + "\\n"
            )

    except Exception as e:
        print("Router log error:", e)


def channel_name(shop):
    name = (
        shop.lower()
        .strip()
        .replace("**", "")
        .replace("🏪", "")
        .replace("sklep:", "")
        .replace("shop:", "")
        .replace("https://", "")
        .replace("http://", "")
        .replace("www.", "")
        .replace(".pl", "")
        .replace(".com", "")
        .replace("/", "")
    )

    name = (
        name
        .replace(":", "")
        .replace(".", "-")
        .replace(" ", "-")
        .replace("_", "-")
    )

    while "--" in name:
        name = name.replace("--", "-")

    return name.strip("-")

def get_full_text(message):
    text = message.content or ""

    for embed in message.embeds:
        if embed.title:
            text += "\n" + embed.title

        if embed.description:
            text += "\n" + embed.description

        for field in embed.fields:
            text += "\n" + field.name
            text += "\n" + field.value

    return text


def get_shop(message):
    for embed in message.embeds:
        for field in embed.fields:
            field_name = field.name.strip().lower()

            if field_name == "🏪 sklep":
                value = field.value.strip()

                if value and value.lower() != "sklep":
                    return value.lower()

    return None

def get_system_type(message):
    text = get_full_text(message).lower()

    if "alarm" in text or "🚨" in text:
        return ERROR_CHANNEL_NAME

    if "heartbeat" in text or "monitor działa" in text:
        return HEARTBEAT_CHANNEL_NAME

    if "uruchomiony" in text or "router online" in text:
        return STATUS_CHANNEL_NAME

    return None




async def sort_pokemon_channels(guild):
    """Sort channels alphabetically across all Pokemon categories (50 per cat)."""
    main_cat = guild.get_channel(CATEGORY_ID)
    if not main_cat:
        return
    cat_base = main_cat.name.rstrip(" 0123456789")

    # Collect all pokemon categories
    pokemon_cats = [main_cat]
    num = 2
    while True:
        cat = discord.utils.get(guild.categories, name=f"{cat_base} {num}")
        if not cat:
            break
        pokemon_cats.append(cat)
        num += 1

    # Collect all shop channels from all pokemon categories
    all_shops = []
    monitor = None
    for cat in pokemon_cats:
        for c in guild.text_channels:
            if c.category_id == cat.id:
                if c.name == MONITOR_CHANNEL_NAME:
                    monitor = c
                else:
                    all_shops.append(c)

    # Move monitor-pokemon to system category if not there already
    if monitor:
        sys_cat = discord.utils.get(guild.categories, name=SYSTEM_CATEGORY_NAME)
        if sys_cat and monitor.category_id != sys_cat.id:
            try:
                await monitor.edit(category=sys_cat, position=0)
                print(f"[SORTER] Przeniesiono {MONITOR_CHANNEL_NAME} do {SYSTEM_CATEGORY_NAME}")
            except Exception as e:
                print(f"[SORTER] Blad przenoszenia monitor: {e}")

    # Sort all shops alphabetically
    all_shops.sort(key=lambda x: x.name.lower())

    # Distribute into categories (50 per category)
    chunks = []
    for i in range(0, len(all_shops), 50):
        chunks.append(all_shops[i:i+50])

    # Ensure we have enough categories
    while len(chunks) > len(pokemon_cats):
        new_name = f"{cat_base} {len(pokemon_cats) + 1}"
        new_cat = await guild.create_category(new_name)
        pokemon_cats.append(new_cat)
        print(f"[SORTER] Utworzono kategorie: {new_name}")

    # Move channels to correct categories and set positions
    for cat_idx, chunk in enumerate(chunks):
        cat = pokemon_cats[cat_idx]
        for pos, channel in enumerate(chunk):
            needs_move = channel.category_id != cat.id
            needs_pos = channel.position != pos
            if needs_move:
                try:
                    await channel.edit(category=cat, position=pos)
                except Exception as e:
                    print(f"[SORTER] Blad move {channel.name}: {e}")
            elif needs_pos:
                try:
                    await channel.edit(position=pos)
                except Exception as e:
                    pass

    print(f"[SORTER] Posortowano {len(all_shops)} kanalow w {len(chunks)} kategoriach")

async def channel_sorter():
    """Sort co 30min."""
    await client.wait_until_ready()
    while not client.is_closed():
        await asyncio.sleep(1800)
        guild = client.get_guild(GUILD_ID)
        if guild:
            try: await sort_pokemon_channels(guild)
            except Exception as e: print("[SORTER]",e)


async def get_or_create_shop_channel(guild, shop):
    name = channel_name(shop)
    if name in channel_locks and isinstance(channel_locks[name], discord.TextChannel):
        return channel_locks[name]
    async with channel_lock_master:
        if name in channel_locks and isinstance(channel_locks[name], discord.TextChannel):
            return channel_locks[name]
        for ch in guild.text_channels:
            if channel_name(ch.name) == name:
                channel_locks[name] = ch
                return ch
        # Route to correct category based on shop type
        shop_lower = shop.lower() if shop else ""
        if any(ls in shop_lower for ls in LEGO_SHOPS):
            category = discord.utils.get(guild.categories, name=LEGO_CATEGORY_NAME)
            if not category:
                category = await guild.create_category(LEGO_CATEGORY_NAME)
                print(f"Utworzono kategorie: {LEGO_CATEGORY_NAME}")
        elif any(fs in shop_lower for fs in FOREIGN_SHOPS):
            category = discord.utils.get(guild.categories, name=FOREIGN_CATEGORY_NAME)
            if not category:
                category = await guild.create_category(FOREIGN_CATEGORY_NAME)
                print(f"Utworzono kategorie: {FOREIGN_CATEGORY_NAME}")
        else:
            category = guild.get_channel(CATEGORY_ID)
        try:
            t = await guild.create_text_channel(name=name, category=category)
        except discord.HTTPException as e:
            if "Maximum number of channels" in str(e):
                cat_base = category.name.rstrip(" 0123456789") if category else "Pokemon"
                num = 2
                while True:
                    new_name = f"{cat_base} {num}"
                    new_cat = discord.utils.get(guild.categories, name=new_name)
                    if not new_cat:
                        new_cat = await guild.create_category(new_name)
                        print(f"Utworzono kategorie: {new_name}")
                    if len([c for c in guild.channels if c.category_id == new_cat.id]) < 50:
                        t = await guild.create_text_channel(name=name, category=new_cat)
                        break
                    num += 1
            else:
                raise
        channel_locks[name] = t
        print("Utworzono kanal sklepu:", name)
        return t


async def get_or_create_system():

    guild = client.get_guild(GUILD_ID)

    if not guild:
        print("Brak serwera")
        return

    category = discord.utils.get(
        guild.categories,
        name=SYSTEM_CATEGORY_NAME
    )

    if not category:
        category = await guild.create_category(
            SYSTEM_CATEGORY_NAME
        )
        print("Utworzono kategorię:", SYSTEM_CATEGORY_NAME)


    for name in [
        STATUS_CHANNEL_NAME,
        HEARTBEAT_CHANNEL_NAME,
        ERROR_CHANNEL_NAME
    ]:

        channel = discord.utils.get(
            guild.text_channels,
            name=name
        )

        if not channel:
            channel = await guild.create_text_channel(
                name=name,
                category=category
            )

            print("Utworzono kanał:", name)

        system_channels[name] = channel



async def send_system(name, content, embeds=None):

    channel = system_channels.get(name)

    if channel:
        await channel.send(
            content=content,
            embeds=embeds or []
        )



async def get_monitor_channel(guild):

    channel = discord.utils.get(
        guild.text_channels,
        name=MONITOR_CHANNEL_NAME
    )

    if not channel:

        category = guild.get_channel(
            CATEGORY_ID
        )

        channel = await guild.create_text_channel(
            name=MONITOR_CHANNEL_NAME,
            category=category
        )

        print(
            "Utworzono monitor:",
            MONITOR_CHANNEL_NAME
        )

    return channel



def check_service(name):

    try:

        result = subprocess.run(
            [
                "systemctl",
                "is-active",
                name
            ],
            capture_output=True,
            text=True
        )

        return result.stdout.strip()

    except:

        return "unknown"



async def watchdog():

    await client.wait_until_ready()

    while not client.is_closed():

        monitor = check_service(
            "pokemon-monitor-v2"
        )

        router = check_service(
            "discord-router"
        )

        if monitor != "active" or router != "active":

            await send_system(
                ERROR_CHANNEL_NAME,
                (
                    "🚨 ALARM SYSTEMU\n\n"
                    f"pokemon-monitor-v2: {monitor}\n"
                    f"discord-router: {router}"
                )
            )

        await asyncio.sleep(300)



@client.event
async def on_ready():

    print(
        "Router online:",
        client.user
    )

    await get_or_create_system()

    guild = client.get_guild(GUILD_ID)
    if guild:
        await sort_pokemon_channels(guild)
        # WAS DISABLED: sortowanie kanałów nie może działać na każdą wiadomość
    # # DISABLED: sortowanie kanałów nie może działać na każdą wiadomość
    # await sort_pokemon_channels(guild)

    await send_system(
        STATUS_CHANNEL_NAME,
        "💚 Pokemon Router online"
    )

    client.loop.create_task(watchdog())
    client.loop.create_task(channel_sorter())



@client.event
async def on_message(message):

    if message.author == client.user:
        return


    if message.channel.id != SOURCE_CHANNEL_ID:
        return


    shop = get_shop(message)


    if shop:

        guild = message.guild


        # ZBIORCZY MONITOR - wylaczony (webhook juz trafia do monitor-pokemon)


        # KANAŁ SKLEPU (z lockiem)
        target = await get_or_create_shop_channel(guild, shop)
        name = channel_name(shop)


        await target.send(
            content=message.content,
            embeds=message.embeds
        )


        # DISABLED: sortowanie kanałów nie może działać na każdą wiadomość
    # # DISABLED: sortowanie kanałów nie może działać na każdą wiadomość
    # await sort_pokemon_channels(guild)

        router_log(
            "SHOP_ROUTED",
            {
                "shop": shop,
                "channel": name
            }
        )

        print(
            "Sklep:",
            name
        )

        return



    system = get_system_type(message)


    if system:

        await send_system(
            system,
            message.content,
            message.embeds
        )

        print(
            "System:",
            system
        )



client.run(TOKEN)
