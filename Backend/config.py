import os
from pathlib import Path
from dotenv import load_dotenv

# PATH SETUP — Backend root is this package (code/Backend)
BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_DIR = BASE_DIR / "credentials"
AI_DIR = BASE_DIR / "ai"

# Ensure `import ai...`, `import api...`, `import db...` resolve when running from Backend root
_backend_root = str(BASE_DIR)
if _backend_root not in os.sys.path:
    os.sys.path.insert(0, _backend_root)

# LOAD CREDENTIAL FILES
env_files = [
    CREDENTIALS_DIR / "backend.env",
]

for env_file in env_files:
    if env_file.exists():
        load_dotenv(env_file)

# APPLICATION FLAGS
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
DEBUG = os.environ.get("DEBUG", "1") in ("1", "true", "True")
IS_FLASK = True

# THIRD-PARTY API KEYS (dashboard / cards — crawl keys live in Data-Crawler-Task)
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")

GOOGLE_TRENDS_GEO = os.environ.get("GOOGLE_TRENDS_GEO", "AU")
GOOGLE_TRENDS_TZ = int(os.environ.get("GOOGLE_TRENDS_TZ", "-660"))

# MONGODB
MONGODB_URI = os.environ.get("MONGODB_URI")
MONGODB_DBNAME = os.environ.get("MONGODB_DBNAME", "pace_database")

# SERVER CONFIG
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
