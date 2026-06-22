"""
config/settings.py
─────────────────
Central configuration for the Video Automation Agent.
All values are read from environment variables (set as GitHub Secrets).
"""

import os
import json
import base64
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


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

# ─── Google Drive ──────────────────────────────────────────────────────────────
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "")   # Destination folder ID

# ─── Google Credentials ────────────────────────────────────────────────────────
# GitHub Secret में base64-encoded JSON है
_CREDS_B64      = os.environ.get("GOOGLE_CREDENTIALS", "")

def get_google_credentials_dict() -> dict:
    """Base64 encoded service account JSON को decode करके dict return करता है।"""
    if not _CREDS_B64:
        raise ValueError("GOOGLE_CREDENTIALS environment variable not set!")
    decoded = base64.b64decode(_CREDS_B64).decode("utf-8")
    return json.loads(decoded)

# ─── AI Video Website ──────────────────────────────────────────────────────────
# NOTE: यह section आपकी specific website के अनुसार customize करें

WEBSITE_URL      = os.environ.get("WEBSITE_URL", "https://klingai.com")  # Video generation site
WEBSITE_EMAIL    = os.environ.get("WEBSITE_EMAIL", "")
WEBSITE_PASSWORD = os.environ.get("WEBSITE_PASSWORD", "")

# Playwright browser settings
BROWSER_HEADLESS = os.environ.get("BROWSER_HEADLESS", "true").lower() == "true"
BROWSER_SLOW_MO  = int(os.environ.get("BROWSER_SLOW_MO", "100"))  # ms, human-like speed

# Video generation timeout (seconds) — website के speed के अनुसार बदलें
VIDEO_GEN_TIMEOUT_SEC = int(os.environ.get("VIDEO_GEN_TIMEOUT_SEC", "600"))  # 10 minutes max

# ─── Schedule ─────────────────────────────────────────────────────────────────
MAX_VIDEOS_PER_RUN    = int(os.environ.get("MAX_VIDEOS_PER_RUN", "1"))  # एक run में कितने videos
PROMPTS_PER_VIDEO     = int(os.environ.get("PROMPTS_PER_VIDEO", "3"))   # हर video के कितने prompts

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
