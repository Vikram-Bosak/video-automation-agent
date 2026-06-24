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

# ─── Google Sheets ─────────────────────────────────────────────────────────────
SHEET_ID        = os.environ.get("SHEET_ID", "")          # Sheet URL का ID part
SHEET_NAME      = os.environ.get("SHEET_NAME", "Sheet1")  # Tab name
SHEET_RANGE     = os.environ.get("SHEET_RANGE", "A:I")    # पढ़ने का range

# Column mapping (0-indexed) — अपने sheet के अनुसार बदलें
COL_DAY         = int(os.environ.get("COL_DAY",         "0"))  # Column A = Day
COL_CATEGORY    = int(os.environ.get("COL_CATEGORY",    "1"))  # Column B = Category
COL_TITLE       = int(os.environ.get("COL_TITLE",       "2"))  # Column C = Title
COL_TOPIC       = int(os.environ.get("COL_TOPIC",       "3"))  # Column D = Topic
COL_SCENE       = int(os.environ.get("COL_SCENE",       "4"))  # Column E = Scene
COL_SCENE_LABEL = int(os.environ.get("COL_SCENE_LABEL", "5"))  # Column F = Scene_Label
COL_PROMPT      = int(os.environ.get("COL_PROMPT",      "6"))  # Column G = Prompt
COL_STATUS      = int(os.environ.get("COL_STATUS",      "7"))  # Column H = Status
COL_DRIVE_LINK  = int(os.environ.get("COL_DRIVE_LINK",  "8"))  # Column I = Video_File (Drive Link)


STATUS_PENDING  = "pending"
STATUS_RUNNING  = "running"
STATUS_DONE     = "done"
STATUS_FAILED   = "failed"

# ─── Stuck Row Recovery ───────────────────────────────────────────────────────
# "running" status में इतने पुराने rows को automatically retry करो (hours)
STUCK_ROW_TIMEOUT_HOURS = int(os.environ.get("STUCK_ROW_TIMEOUT_HOURS", "3"))

# ─── Google Drive ──────────────────────────────────────────────────────────────
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "")   # Destination folder ID

# ─── Google Credentials ────────────────────────────────────────────────────────
# GitHub Secret में base64-encoded JSON है
_CREDS_B64      = os.environ.get("GOOGLE_CREDENTIALS", "")

def get_google_credentials_dict() -> dict:
    """Base64 encoded service account JSON को decode करके dict return करता है।"""
    if not _CREDS_B64:
        raise ValueError(
            "❌ GOOGLE_CREDENTIALS environment variable not set!\n"
            "   GitHub Secrets में जाकर GOOGLE_CREDENTIALS set करें।\n"
            "   Command: base64 -w 0 service_account.json"
        )
    try:
        decoded = base64.b64decode(_CREDS_B64).decode("utf-8")
    except Exception as e:
        raise ValueError(
            f"❌ GOOGLE_CREDENTIALS invalid base64! Error: {e}\n"
            "   Secret को फिर से encode करें: base64 -w 0 service_account.json"
        )
    try:
        return json.loads(decoded)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"❌ GOOGLE_CREDENTIALS valid base64 but invalid JSON! Error: {e}\n"
            "   Secret में valid service account JSON होना चाहिए।"
        )

# ─── AI Video Website ──────────────────────────────────────────────────────────
WEBSITE_URL      = os.environ.get("WEBSITE_URL", "https://klingai.com")
WEBSITE_EMAIL    = os.environ.get("WEBSITE_EMAIL", "")
WEBSITE_PASSWORD = os.environ.get("WEBSITE_PASSWORD", "")

# Playwright browser settings
BROWSER_HEADLESS = os.environ.get("BROWSER_HEADLESS", "true").lower() == "true"
BROWSER_SLOW_MO  = int(os.environ.get("BROWSER_SLOW_MO", "100"))

# Video generation timeout (seconds)
VIDEO_GEN_TIMEOUT_SEC = int(os.environ.get("VIDEO_GEN_TIMEOUT_SEC", "600"))  # 10 minutes max

# ─── Video Output Settings ────────────────────────────────────────────────────
VIDEO_DURATION_SEC  = int(os.environ.get("VIDEO_DURATION_SEC", "24"))  # Total video length (seconds)
VIDEO_ASPECT_RATIO  = os.environ.get("VIDEO_ASPECT_RATIO", "9:16")    # Portrait for shorts/reels
VIDEO_POLL_INTERVAL_SEC = int(os.environ.get("VIDEO_POLL_INTERVAL_SEC", "10"))
VIDEO_MAX_WAIT_SEC      = int(os.environ.get("VIDEO_MAX_WAIT_SEC", "600"))

# ─── Schedule ─────────────────────────────────────────────────────────────────
MAX_VIDEOS_PER_RUN    = int(os.environ.get("MAX_VIDEOS_PER_RUN", "3"))
PROMPTS_PER_VIDEO     = int(os.environ.get("PROMPTS_PER_VIDEO", "3"))

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


# ─── Health Check ──────────────────────────────────────────────────────────────
def validate_config() -> list[str]:
    """
    Startup पर सभी required env vars validate करो।
    Returns: list of error messages (empty = all OK)
    """
    errors = []

    if not SHEET_ID:
        errors.append("SHEET_ID not set")
    if not DRIVE_FOLDER_ID:
        errors.append("DRIVE_FOLDER_ID not set")

    # Credentials check
    if not _CREDS_B64:
        errors.append("GOOGLE_CREDENTIALS not set")
    else:
        try:
            get_google_credentials_dict()
        except ValueError as e:
            errors.append(str(e))

    # Website config check
    if "docs.google.com/videos" not in WEBSITE_URL and "google" in WEBSITE_URL.lower():
        pass  # Google Vids — OK
    elif not WEBSITE_URL or WEBSITE_URL == "https://klingai.com":
        errors.append("WEBSITE_URL not configured (using default klingai.com)")

    # Cookies check
    cookies_file = BASE_DIR / "cookies.json"
    if cookies_file.exists():
        try:
            data = json.loads(cookies_file.read_text())
            if not data.get("cookies") and not data.get("origins"):
                errors.append("cookies.json exists but is empty/invalid")
        except (json.JSONDecodeError, Exception):
            errors.append("cookies.json exists but is corrupted")
    else:
        errors.append("cookies.json not found — Google login needed")

    return errors
