import os

from dotenv import load_dotenv

load_dotenv()


def _split(env_val: str) -> list[str]:
    return [x.strip() for x in env_val.split(",") if x.strip()]


# ---- Telegram ----
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in _split(os.getenv("ADMIN_IDS", ""))]

# Channels users must join before using the bot, e.g. "@mychannel,@mychannel2"
FORCE_JOIN_CHANNELS = _split(os.getenv("FORCE_JOIN_CHANNELS", ""))

# ---- PasarGuard panel ----
PANEL_URL = os.getenv("PANEL_URL", "").rstrip("/")
PANEL_USERNAME = os.getenv("PANEL_USERNAME", "")
PANEL_PASSWORD = os.getenv("PANEL_PASSWORD", "")
_group_ids = _split(os.getenv("PANEL_GROUP_IDS", ""))
PANEL_GROUP_IDS = [int(x) for x in _group_ids] if _group_ids else None

# ---- Payment (manual card-to-card) ----
CARD_NUMBER = os.getenv("CARD_NUMBER", "0000-0000-0000-0000")
CARD_HOLDER = os.getenv("CARD_HOLDER", "نام صاحب کارت")
CURRENCY = os.getenv("CURRENCY", "تومان")

# ---- Trial account ----
TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "1"))
TRIAL_GB = int(os.getenv("TRIAL_GB", "1"))

# ---- Storage ----
DB_PATH = os.getenv("DB_PATH", "data/bot.db")
