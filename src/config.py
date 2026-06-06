import os
from dotenv import load_dotenv

load_dotenv()

CLUB_ID: str = os.environ["CLUB_ID"]
WP_URL: str = os.environ["WP_URL"].rstrip("/")
WP_USER: str = os.environ["WP_USER"]
WP_APP_PASSWORD: str = os.environ["WP_APP_PASSWORD"]

CACHE_TTL: int = int(os.getenv("CACHE_TTL", "3600"))
FONT_CACHE_TTL: int = int(os.getenv("FONT_CACHE_TTL", "86400"))

FUSSBALL_DE_BASE_URL = "https://www.fussball.de"
