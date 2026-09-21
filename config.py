"""
Only values that must exist before the database is even opened live here.
Everything else (bot token, admin ids, panel credentials, force-join
channels, payment info, mini-app theme...) is configured live from inside
the bot's admin panel and stored in the `settings` table — see settings.py.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# Railway (and most PaaS) inject PORT automatically.
PORT = int(os.getenv("PORT", "8080"))

DB_PATH = os.getenv("DB_PATH", "data/bot.db")
