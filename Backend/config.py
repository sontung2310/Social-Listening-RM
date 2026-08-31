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

# ARTICLE / AI MONGODB
# Existing names remain fallbacks for current deployments.
ARTICLE_MONGODB_URI = os.environ.get("ARTICLE_MONGODB_URI") or os.environ.get("MONGODB_URI")
ARTICLE_MONGODB_DBNAME = (
    os.environ.get("ARTICLE_MONGODB_DBNAME")
    or os.environ.get("MONGODB_DBNAME", "pace_database")
)
MONGODB_URI = ARTICLE_MONGODB_URI
MONGODB_DBNAME = ARTICLE_MONGODB_DBNAME

# DASHBOARD INFLUENCER-LIST MONGODB (separate host/database)
DASHBOARD_DATABASE_HOST = (os.environ.get("DASHBOARD_DATABASE_HOST") or "").strip()
DASHBOARD_DATABASE_NAME = (os.environ.get("DASHBOARD_DATABASE_NAME") or "").strip()
DASHBOARD_DATABASE_USERNAME = (os.environ.get("DASHBOARD_DATABASE_USERNAME") or "").strip()
DASHBOARD_DATABASE_PASSWORD = (os.environ.get("DASHBOARD_DATABASE_PASSWORD") or "").strip()
# Data-Crawler-Task is the source of truth for influencer task state. Pace
# keeps the command facade but does not consume influencer result events.
DCT_API_BASE_URL = (
    os.environ.get("DCT_API_BASE_URL") or "http://127.0.0.1:8001"
).strip().rstrip("/")
DCT_API_KEY = (os.environ.get("DCT_API_KEY") or "").strip()
DCT_API_TIMEOUT_SECONDS = float(os.environ.get("DCT_API_TIMEOUT_SECONDS", "10"))

# SERVER CONFIG
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

# AI WORKER QUEUE — "sim" (fixtures) or "sqs" (real AWS)
AI_QUEUE_BACKEND = os.environ.get("AI_QUEUE_BACKEND", "sim")
AI_WORKER_MAX_MESSAGES = int(os.environ.get("AI_WORKER_MAX_MESSAGES", "20"))
AI_WORKER_IDLE_SLEEP_SECONDS = float(os.environ.get("AI_WORKER_IDLE_SLEEP_SECONDS", "1"))

# AWS / SQS
AWS_ACCESS_KEY_ID = (os.environ.get("AWS_ACCESS_KEY_ID") or "").strip()
AWS_SECRET_ACCESS_KEY = (os.environ.get("AWS_SECRET_ACCESS_KEY") or "").strip()
AWS_REGION = (os.environ.get("AWS_REGION") or "ap-southeast-2").strip()
SQS_COMMAND_QUEUE_URL = (os.environ.get("SQS_COMMAND_QUEUE_URL") or "").strip()
SQS_AI_QUEUE_URL = (os.environ.get("SQS_AI_QUEUE_URL") or "").strip()
SQS_DLQ_URL = (os.environ.get("SQS_DLQ_URL") or "").strip()
SQS_WAIT_TIME_SECONDS = int(os.environ.get("SQS_WAIT_TIME_SECONDS", "20"))
