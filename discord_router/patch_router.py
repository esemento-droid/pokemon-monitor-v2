import re
with open('/opt/discord-router/router.py', 'r') as f:
    c = f.read()
c = c.replace('system_channels = {}', 'system_channels = {}
channel_locks = {}
channel_lock_master = asyncio.Lock()')
old_block = '''        # KANAŁ SKLEPU

        name = channel_name(shop)

        target = None

        # SZUKANIE ISTNIEJĄCEGO KANAŁU PO NORMALIZACJI
        for ch in guild.text_channels:
            if channel_name(ch.name) == name:
                target = ch
                break

        if not target:

            category = guild.get_channel(
                CATEGORY_ID
            )

            await asyncio.sleep(1)
            target = await guild.create_text_channel(
                name=name,
                category=category
            )

            print(
                "Utworzono kanał sklepu:",
                name
            )'''
new_block = '''        # KANAŁ SKLEPU (z lockiem)
        target = await get_or_create_shop_channel(guild, shop)'''
c = c.replace(old_block, new_block)
func = '''
async def channel_sorter():
    await client.wait_until_ready()
    while not client.is_closed():
        await asyncio.sleep(1800)
        guild = client.get_guild(GUILD_ID)
        if guild:
            try:
                await sort_pokemon_channels(guild)
            except Exception as e:
                print("[SORTER ERROR]", e)

async def get_or_create_shop_channel(guild, shop):
    name = channel_name(shop)
    async with channel_lock_master:
        if name not in channel_locks:
            channel_locks[name] = asyncio.Lock()
    async with channel_locks[name]:
        for ch in guild.text_channels:
            if channel_name(ch.name) == name:
                return ch
        category = guild.get_channel(CATEGORY_ID)
        target = await guild.create_text_channel(name=name, category=category)
        print("Utworzono kanał sklepu:", name)
        return target

'''
c = c.replace('async def get_or_create_system():', func + 'async def get_or_create_system():')
c = c.replace('''    if guild:
        pass
        # DISABLED: sortowanie kanałów nie może działać na każdą wiadomość
    # # DISABLED: sortowanie kanałów nie może działać na każdą wiadomość
    # await sort_pokemon_channels(guild)''', '''    if guild:
        await sort_pokemon_channels(guild)''')
c = c.replace('    client.loop.create_task(
        watchdog()
    )', '    client.loop.create_task(watchdog())
    client.loop.create_task(channel_sorter())')
with open('/opt/discord-router/router.py', 'w') as f:
    f.write(c)
print("PATCHED OK")
