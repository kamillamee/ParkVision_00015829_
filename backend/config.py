import os
import secrets
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

DATABASE_PATH = BASE_DIR / "database" / "parking.db"

# APP_ENV=prod refuses to start without a real SECRET_KEY / AI_API_KEY.
# In dev we auto-generate ephemeral secrets (different every restart), which
# invalidates existing JWTs but guarantees we never ship the baked-in demo key.
APP_ENV = os.getenv("APP_ENV", "dev").lower()

_DEFAULT_SECRET_SENTINEL = "your-secret-key-change-in-production-12345"
_DEFAULT_AI_KEY_SENTINEL = "ai-module-secret-key-12345"

SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if not SECRET_KEY or SECRET_KEY == _DEFAULT_SECRET_SENTINEL:
    if APP_ENV == "prod":
        sys.stderr.write(
            "FATAL: SECRET_KEY must be set to a non-default value when APP_ENV=prod.\n"
        )
        raise SystemExit(1)
    SECRET_KEY = secrets.token_urlsafe(48)
    print(
        "WARN: SECRET_KEY not set — generated an ephemeral dev key. "
        "Set SECRET_KEY=<random> to keep JWT sessions across restarts."
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60

AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
if not AI_API_KEY or AI_API_KEY == _DEFAULT_AI_KEY_SENTINEL:
    if APP_ENV == "prod":
        sys.stderr.write(
            "FATAL: AI_API_KEY must be set to a non-default value when APP_ENV=prod.\n"
        )
        raise SystemExit(1)
    # Dev default — intentionally a known value so local AI module + backend
    # can connect without extra config. Never accepted in prod.
    AI_API_KEY = _DEFAULT_AI_KEY_SENTINEL
    print(
        "WARN: AI_API_KEY using dev default. "
        "Set AI_API_KEY=<random> before deploying."
    )

CHAT_ENABLED = os.getenv("CHAT_ENABLED", "true").lower() == "true"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
CHAT_RATE_LIMIT = os.getenv("CHAT_RATE_LIMIT", "20/minute")
AUTH_RATE_LIMIT = os.getenv("AUTH_RATE_LIMIT", "10/minute")

DEBUG = os.getenv("DEBUG", "True").lower() == "true"
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", 8000))

VIDEO_PATH = BASE_DIR / "video" / "bmu.mp4"
VIDEO_PATH_WEST = BASE_DIR / "video" / "west.mp4"
MODEL_PATH = BASE_DIR / "models" / "yolo11m.pt"
SLOTS_CONFIG = BASE_DIR / "config" / "bmu.json"
SLOTS_CONFIG_WEST = BASE_DIR / "config" / "west.json"

PARKING_VISION_ENABLED = os.getenv("PARKING_VISION_ENABLED", "true").lower() == "true"
PARKING_VISION_DETECT_FPS = float(os.getenv("PARKING_VISION_DETECT_FPS", "8"))
PARKING_VISION_FRAME_SKIP = int(os.getenv("PARKING_VISION_FRAME_SKIP", "2"))
PARKING_VISION_DISPLAY_FPS = float(os.getenv("PARKING_VISION_DISPLAY_FPS", "24"))
PARKING_VISION_STREAM_QUALITY = int(os.getenv("PARKING_VISION_STREAM_QUALITY", "82"))
PARKING_VISION_INFER_W = int(os.getenv("PARKING_VISION_INFER_W", "0"))
PARKING_VISION_INFER_H = int(os.getenv("PARKING_VISION_INFER_H", "0"))
PARKING_VISION_USE_TRACK = os.getenv("PARKING_VISION_USE_TRACK", "false").lower() == "true"
PARKING_VISION_CONF = os.getenv("PARKING_VISION_CONF", "").strip()
PARKING_VISION_DISABLE_ROI = os.getenv("PARKING_VISION_DISABLE_ROI", "").lower() in ("1", "true", "yes", "on")

NOTIFY_EMAIL_ENABLED = os.getenv("NOTIFY_EMAIL_ENABLED", "true").lower() == "true"
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "noreply@smartvision.local")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

NOTIFY_SMS_ENABLED = os.getenv("NOTIFY_SMS_ENABLED", "false").lower() == "true"
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
