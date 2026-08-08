import os, sys, asyncio, random, logging, signal
from logging.handlers import RotatingFileHandler

DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(DIR, "venv", "bin", "python3")
RUNNER = os.path.join(DIR, "runner.py")
SHOPS_DIR = os.path.join(DIR, "shops")
LOG_PATH = os.path.join(DIR, "data", "monitor.log")
CHECK_MIN = 5
CHECK_MAX = 20
SLOW_SHOPS = {"tantis", "am76", "proshop", "rgfk", "blindbox", "flamberg", "mrpuggy", "pikashop", "paladynat", "czytam", "swiatkart"}
SHOPIFY_SHOPS = {"pokeloot", "skladgier"}
PW_SHOPS = {"boosterpoint", "strefakart", "strefamtg", "empik"}
SLOW_MIN = 45
SLOW_MAX = 90
SHOPIFY_MIN = 180
SHOPIFY_MAX = 300
PW_MIN = 90
PW_MAX = 180
TIMEOUT = 300

logger = logging.getLogger("orchestrator")
logger.setLevel(logging.INFO)
fh = RotatingFileHandler(LOG_PATH, maxBytes=5*1024*1024, backupCount=3)
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(fh)
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(ch)

def get_shops():
    return [f[:-3] for f in sorted(os.listdir(SHOPS_DIR)) if f.endswith(".py") and not f.startswith("__") and f not in ("base.py","template.py")]

async def run_scraper(name):
    try:
        proc = await asyncio.create_subprocess_exec(VENV_PYTHON,"-u",RUNNER,name,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,cwd=DIR,start_new_session=True)
        try:
            stdout,stderr = await asyncio.wait_for(proc.communicate(),timeout=TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(f"[{name}] TIMEOUT {TIMEOUT}s")
            try: os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            await proc.wait()
            return False
        output = stdout.decode().strip()
        if output:
            for line in output.split("\n"):
                if line.strip(): logger.info(line.strip())
        if proc.returncode != 0 and stderr:
            logger.error(f"[{name}] EXIT {proc.returncode}: {stderr.decode().strip()[-200:]}")
            return False
        return True
    except Exception as e:
        logger.error(f"[{name}] EXCEPTION: {e}")
        return False

async def shop_worker(name):
    await asyncio.sleep(random.uniform(0,10))
    errors = 0
    while True:
        success = await run_scraper(name)
        if success:
            errors = 0
            delay = random.randint(SHOPIFY_MIN,SHOPIFY_MAX) if name in SHOPIFY_SHOPS else random.randint(PW_MIN,PW_MAX) if name in PW_SHOPS else random.randint(SLOW_MIN,SLOW_MAX) if name in SLOW_SHOPS else random.randint(CHECK_MIN,CHECK_MAX)
        else:
            errors += 1
            delay = min(60*(2**min(errors//3,3)),300)
        await asyncio.sleep(delay)

async def main():
    logger.info("="*50)
    logger.info("Pokemon Monitor v2 - ORCHESTRATOR START (asyncio)")
    shops = get_shops()
    logger.info(f"{len(shops)} sklepow - wszystkie jednoczesnie")
    tasks = [asyncio.create_task(shop_worker(s)) for s in shops]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
