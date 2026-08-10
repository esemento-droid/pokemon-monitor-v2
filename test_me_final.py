import asyncio, sys, os
os.environ["DISPLAY"] = ":99"
sys.path.insert(0, ".")
from shops.mediaexpert import get_products

async def main():
    p = await get_products()
    for x in p:
        print(x["name"], "|", x["price"], "|", x["available"])
    print("TOTAL:", len(p))

asyncio.run(main())
