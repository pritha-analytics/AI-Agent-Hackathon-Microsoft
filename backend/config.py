import os

from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Centralized store for customer interaction history and Next Best Action
# (offer impression/click) data - see db.py. Point this at a shared, hosted
# Postgres instance (e.g. a free Neon/Supabase project) so everyone running
# this app sees the same data instead of an isolated local file; falls back
# to a local SQLite file when unset, so the app still runs standalone.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///" + os.path.join(os.path.dirname(__file__), "nba.db"))
