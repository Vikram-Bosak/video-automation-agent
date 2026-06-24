"""
main.py
───────
Video Automation Pipeline — FREE version
Har 4 ghante mein 1 video generate karo.

Flow:
  1. Google Sheet se next pending row padho (Title + 3 Prompts)
  2. 3 Prompts se FREE images generate karo (Pollinations.ai)
  3. FFmpeg se animated video banao (Ken Burns effect)
  4. Google Drive par upload karo
  5. Sheet mein "done" mark karo

Cost: ₹0 | No API key | No browser | No billing
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

from config.settings import LOGS_DIR, LOG_LEVEL
from agents.sheet_reader import SheetReader, VideoRow
from agents.video_generator import generate_video
from agents.drive_uploader import DriveUploader
from agents.state_manager import StateManager

# ─── Logging Setup ─────────────────────────────────────────────────────────────

def setup_logging() -> None:
    run_id = int(time.time())
    log_file = LOGS_DIR / f"run_{run_id}.log"

    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(log_file), encoding="utf-8"),
    ]

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format=fmt,
        datefmt=datefmt,
        handlers=handlers,
    )

    for noisy in ["googleapiclient", "urllib3", "httpx", "httpcore"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# ─── Main Pipeline ─────────────────────────────────────────────────────────────

def run_pipeline() -> int:
    """
    Main pipeline — 1 run = 1 video.
    Returns: Exit code (0=success, 1=error, 2=no pending)
    """
    setup_logging()

    logger.info("=" * 60)
    logger.info("  🚀 VIDEO AUTOMATION PIPELINE (FREE)")
    logger.info("  💰 Cost: ₹0 | Method: Pollinations.ai + FFmpeg")
    logger.info("=" * 60)

    state = None
    sheet = None
    drive = None
    row = None

    try:
        state = StateManager()
        sheet = SheetReader()
        drive = DriveUploader()

        # ── Step 1: Next pending row padho ────────────────────────────────
        logger.info("\n📋 STEP 1: Google Sheet se pending row dhundh rahe hain...")

        row = sheet.get_next_pending_row()

        if row is None:
            logger.info("✅ Koi pending row nahi — pipeline band ho rahi hai.")
            state.no_pending()
            return 2

        logger.info(f"✅ Mili: Rows {row.row_indices} | Title: '{row.title}'")
        prompts = row.get_prompts()
        logger.info(f"   Prompts: {len(prompts)}")

        # ── Step 2: Row ko "running" mark karo ────────────────────────────
        sheet.mark_running(row)
        state.begin_run(row.row_index)

        # ── Step 3: FREE Video generate karo ──────────────────────────────
        logger.info(f"\n🎬 STEP 2: FREE video generate kar rahe hain...")
        logger.info(f"   Title: {row.title}")
        logger.info(f"   Method: Pollinations.ai (images) + FFmpeg (video)")

        video_path = generate_video(prompts, row.title)

        if not video_path:
            raise RuntimeError(f"Video generation failed for rows {row.row_indices}")

        size_mb = video_path.stat().st_size / (1024 * 1024)
        logger.info(f"✅ Video ready: {video_path.name} ({size_mb:.1f} MB)")

        # ── Step 4: Google Drive par upload ───────────────────────────────
        logger.info(f"\n☁️  STEP 3: Google Drive upload shuru...")

        drive_links = drive.upload_multiple([video_path])

        if not drive_links:
            raise RuntimeError("Drive upload fail — koi file upload nahi hui")

        logger.info(f"✅ Uploaded: {drive_links[0]}")

        # ── Step 5: Sheet mein "done" mark karo ──────────────────────────
        logger.info(f"\n📊 STEP 4: Sheet mein status update...")
        sheet.mark_done(row, drive_links)
        state.complete_run(row.row_index)

        # ── Cleanup ───────────────────────────────────────────────────────
        try:
            video_path.unlink()
            logger.info("🗑️  Local video file deleted")
        except Exception:
            pass

        # ── Done! ────────────────────────────────────────────────────────
        logger.info("\n" + "=" * 60)
        logger.info("  ✅ PIPELINE COMPLETE!")
        logger.info(f"  📹 Title: {row.title}")
        logger.info(f"  🔗 Drive: {drive_links[0]}")
        logger.info("=" * 60)
        return 0

    except Exception as e:
        logger.error(f"\n❌ PIPELINE ERROR: {e}", exc_info=True)

        if sheet is not None and row is not None:
            try:
                sheet.mark_failed(row, str(e))
            except Exception:
                pass

        if state is not None and row is not None:
            try:
                state.fail_run(row.row_index, str(e))
            except Exception:
                pass

        logger.info("=" * 60)
        logger.info("  ❌ PIPELINE FAILED")
        if row is not None:
            logger.info(f"  Rows: {row.row_indices} | Title: {row.title}")
        logger.info(f"  Error: {str(e)[:200]}")
        logger.info("=" * 60)
        return 1


# ─── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    exit_code = run_pipeline()
    sys.exit(exit_code)
