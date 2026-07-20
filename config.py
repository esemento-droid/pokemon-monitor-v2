import os
from dotenv import load_dotenv
load_dotenv()

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

# Interwały skanowania (sekundy)
CHECK_MIN = 20
CHECK_MAX = 60

# Discord rate limit
DISCORD_MAX_PER_MINUTE = 25

# Baza danych
DB_PATH = "/opt/pokemon-monitor-v2/data/products.db"

# Logi
LOG_PATH = "/opt/pokemon-monitor-v2/data/monitor.log"
