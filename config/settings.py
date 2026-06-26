"""
config/settings.py
─────────────────
Central configuration for the Video Automation Agent.
All values are read from environment variables (set as GitHub Secrets).
"""

import os
import json
import base64
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent.parent
DOWNLOADS_DIR   = BASE_DIR / "downloads"
LOGS_DIR        = BASE_DIR / "logs"
STATE_FILE      = BASE_DIR / "state.json"

DOWNLOADS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ─── Google Cloud ─────────────────────────────────────────────────────────────
GOOGLE_PROJECT_ID = os.environ.get("GOOGLE_PROJECT_ID", "serious-trainer-460603-c9")
GOOGLE_LOCATION   = os.environ.get("GOOGLE_LOCATION", "us-central1")

# ─── Google Sheets ─────────────────────────────────────────────────────────────
SHEET_ID        = os.environ.get("SHEET_ID", "")
SHEET_NAME      = os.environ.get("SHEET_NAME", "Sheet1")
SHEET_RANGE     = os.environ.get("SHEET_RANGE", "A:I")

# Column mapping (0-indexed)
COL_DAY         = int(os.environ.get("COL_DAY",         "0"))
COL_CATEGORY    = int(os.environ.get("COL_CATEGORY",    "1"))
COL_TITLE       = int(os.environ.get("COL_TITLE",       "2"))
COL_TOPIC       = int(os.environ.get("COL_TOPIC",       "3"))
COL_SCENE       = int(os.environ.get("COL_SCENE",       "4"))
COL_SCENE_LABEL = int(os.environ.get("COL_SCENE_LABEL", "5"))
COL_PROMPT      = int(os.environ.get("COL_PROMPT",      "6"))
COL_STATUS      = int(os.environ.get("COL_STATUS",      "7"))
COL_DRIVE_LINK  = int(os.environ.get("COL_DRIVE_LINK",  "8"))

STATUS_PENDING  = "pending"
STATUS_RUNNING  = "running"
STATUS_DONE     = "done"
STATUS_FAILED   = "failed"

# ─── Stuck Row Recovery ───────────────────────────────────────────────────────
STUCK_ROW_TIMEOUT_HOURS = int(os.environ.get("STUCK_ROW_TIMEOUT_HOURS", "3"))

# ─── Google Drive ──────────────────────────────────────────────────────────────
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "")

# ─── Google Credentials ────────────────────────────────────────────────────────
_CREDS_B64 = os.environ.get("GOOGLE_CREDENTIALS", "")

def get_google_credentials_dict() -> dict:
    """Base64 encoded service account JSON decode karo."""
    if not _CREDS_B64:
        raise ValueError(
            "❌ GOOGLE_CREDENTIALS not set!\n"
            "   GitHub Secrets mein set karo: base64 -w 0 service_account.json"
        )
    try:
        decoded = base64.b64decode(_CREDS_B64).decode("utf-8")
    except Exception as e:
        raise ValueError(f"❌ GOOGLE_CREDENTIALS invalid base64: {e}")
    try:
        return json.loads(decoded)
    except json.JSONDecodeError as e:
        raise ValueError(f"❌ GOOGLE_CREDENTIALS invalid JSON: {e}")

# ─── Video Settings ───────────────────────────────────────────────────────────
VIDEO_DURATION_SEC  = int(os.environ.get("VIDEO_DURATION_SEC", "24"))
VIDEO_ASPECT_RATIO  = os.environ.get("VIDEO_ASPECT_RATIO", "9:16")
VIDEO_POLL_INTERVAL_SEC = int(os.environ.get("VIDEO_POLL_INTERVAL_SEC", "10"))
VIDEO_MAX_WAIT_SEC      = int(os.environ.get("VIDEO_MAX_WAIT_SEC", "600"))
VIDEO_GEN_TIMEOUT_SEC   = int(os.environ.get("VIDEO_GEN_TIMEOUT_SEC", "600"))

# ─── Browser Settings (Google Vids automation) ────────────────────────────────
BROWSER_HEADLESS = os.environ.get("BROWSER_HEADLESS", "true").lower() == "true"
BROWSER_SLOW_MO  = int(os.environ.get("BROWSER_SLOW_MO", "100"))

# ─── Veo Model ────────────────────────────────────────────────────────────────
VEEO_MODEL = os.environ.get("VEEO_MODEL", "veo-3.0-generate-001")
VEEO_CLIPS_PER_VIDEO = int(os.environ.get("VEEO_CLIPS_PER_VIDEO", "3"))
VEEO_CLIP_DURATION   = int(os.environ.get("VEEO_CLIP_DURATION", "8"))

# ─── Schedule ─────────────────────────────────────────────────────────────────
MAX_VIDEOS_PER_RUN = int(os.environ.get("MAX_VIDEOS_PER_RUN", "1"))
PROMPTS_PER_VIDEO  = int(os.environ.get("PROMPTS_PER_VIDEO", "3"))

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


# ─── Health Check ──────────────────────────────────────────────────────────────
def validate_config() -> list[str]:
    """Startup pe sab required config validate karo."""
    errors = []

    if not SHEET_ID:
        errors.append("SHEET_ID not set")
    if not DRIVE_FOLDER_ID:
        errors.append("DRIVE_FOLDER_ID not set")

    if not _CREDS_B64:
        errors.append("GOOGLE_CREDENTIALS not set")
    else:
        try:
            get_google_credentials_dict()
        except ValueError as e:
            errors.append(str(e))

    if not GOOGLE_PROJECT_ID:
        errors.append("GOOGLE_PROJECT_ID not set")

    return errors

# ─── LTX-2.3 Settings ────────────────────────────────────────────────────────
LTX_MODEL_PATH    = os.environ.get("LTX_MODEL_PATH", "")  # Empty = auto-download
LTX_DEVICE        = os.environ.get("LTX_DEVICE", "cuda" if os.environ.get("CUDA_VISIBLE_DEVICES") else "cpu")
LTX_QUANTIZATION  = os.environ.get("LTX_QUANTIZATION", "fp8")  # fp8 for 8GB VRAM
