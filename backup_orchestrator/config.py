import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
CHECK_MIN = 5
CHECK_MAX = 15
DISCORD_MAX_PER_MINUTE = 25
DB_PATH = "/opt/pokemon-monitor-v2/data/products.db"
LOG_PATH = "/opt/pokemon-monitor-v2/data/monitor.log"
