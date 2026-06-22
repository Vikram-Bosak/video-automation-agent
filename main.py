"""
main.py
───────
Video Automation Pipeline का main orchestrator।

Website: Google Vids (docs.google.com/videos) — Veo 3.1
Flow:
  1. Google Sheet से next pending row पढ़ो (Title + 3 Prompts)
  2. Google Vids पर 3 × 8s clips generate करो = 24s video
  3. Video download करो, Title के अनुसार rename करो
  4. Google Drive पर upload करो
  5. Sheet में status "done" mark करो
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


from config.settings import LOGS_DIR, LOG_LEVEL, WEBSITE_URL
from agents.sheet_reader  import SheetReader, VideoRow
from agents.google_vids_agent import run_google_vids_agent
from agents.drive_uploader import DriveUploader
from agents.state_manager  import StateManager

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

    # Third-party loggers को quiet करो
    for noisy in ["googleapiclient", "urllib3", "httpx", "httpcore"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# ─── Main Pipeline ─────────────────────────────────────────────────────────────

def run_pipeline() -> int:
    """
    Main pipeline चलाता है।
    Returns: Exit code (0 = success, 1 = error, 2 = no pending rows)
    """
    setup_logging()

    logger.info("=" * 60)
    logger.info("  🚀 VIDEO AUTOMATION PIPELINE STARTING")
    logger.info("=" * 60)

    state = None
    sheet = None
    drive = None
    row = None

    try:
        state   = StateManager()
        sheet   = SheetReader()
        drive   = DriveUploader()

        # ── Step 1: Next pending row पढ़ो ─────────────────────────────────────────
        logger.info("\n📋 STEP 1: Google Sheet से pending row dhundh rahe hain...")

        row = sheet.get_next_pending_row()

        if row is None:
            logger.info("✅ Koi pending row nahi — pipeline band ho rahi hai.")
            state.no_pending()
            return 2   # Exit code 2 = no work to do (not an error)

        logger.info(f"✅ Mili: Rows {row.row_indices} | Title: '{row.title}'")
        logger.info(f"   Prompts: {len(row.get_prompts())}")

        # ── Step 2: Row को "running" mark करो (race condition se bachav) ─────────
        sheet.mark_running(row)
        state.begin_run(row.row_index)

        downloaded_files: list[Path] = []
        drive_links: list[str] = []

        # ── Step 3: Browser agent चलाओ ─────────────────────────────────────
        logger.info(f"\n🌐 STEP 2: Browser agent start kar rahe hain...")
        logger.info(f"   Rows: {row.row_indices} | Title: {row.title}")

        url = WEBSITE_URL.lower()
        if "docs.google.com/videos" in url or "google.com/videos" in url or "vids" in url:
            logger.info("🎬 Using Google Vids Agent")
            downloaded_file = run_google_vids_agent(row)
            if not downloaded_file:
                raise RuntimeError(f"Koi video download nahi hua for rows {row.row_indices}")
            downloaded_files = [downloaded_file]
        else:
            logger.info(f"🎬 Using Browser Agent for: {WEBSITE_URL}")
            from agents.browser_agent import run_browser_agent
            downloaded_files = run_browser_agent(row)
            if not downloaded_files:
                raise RuntimeError(f"Koi video download nahi hua for rows {row.row_indices}")

        logger.info(f"✅ {len(downloaded_files)} video(s) download hui:")
        for f in downloaded_files:
            size_mb = f.stat().st_size / (1024 * 1024)
            logger.info(f"   • {f.name} ({size_mb:.1f} MB)")

        # ── Step 4: Google Drive पर upload ─────────────────────────────────
        logger.info(f"\n☁️  STEP 3: Google Drive upload shuru...")

        drive_links = drive.upload_multiple(downloaded_files)

        if not drive_links:
            raise RuntimeError("Drive upload fail ho gayi — koi file upload nahi hui")

        logger.info(f"✅ {len(drive_links)} file(s) Drive mein upload:")
        for link in drive_links:
            logger.info(f"   🔗 {link}")

        # ── Step 5: Sheet में "done" mark करो ─────────────────────────────
        logger.info(f"\n📊 STEP 4: Sheet mein status update kar rahe hain...")
        sheet.mark_done(row, drive_links)
        state.complete_run(row.row_index)

        # ── Local files cleanup ─────────────────────────────────────────────
        logger.info("🗑️  Local downloaded files cleanup...")
        for f in downloaded_files:
            drive.delete_file_after_upload(f)

        logger.info("\n" + "=" * 60)
        logger.info("  ✅ PIPELINE COMPLETE!")
        logger.info(f"  📹 Title: {row.title}")
        logger.info(f"  📁 Videos uploaded: {len(drive_links)}")
        logger.info(f"  🔗 First link: {drive_links[0] if drive_links else 'N/A'}")
        logger.info("=" * 60)

        _print_summary(state)
        return 0

    except Exception as e:
        logger.error(f"\n❌ PIPELINE ERROR: {e}", exc_info=True)
        
        if sheet is not None and row is not None:
            logger.info("📊 Sheet mein 'failed' mark kar rahe hain...")
            try:
                sheet.mark_failed(row, str(e))
            except Exception as sheet_err:
                logger.error(f"Failed to mark sheet as failed: {sheet_err}")
                
        if state is not None and row is not None:
            try:
                state.fail_run(row.row_index, str(e))
            except Exception as state_err:
                logger.error(f"Failed to mark state as failed: {state_err}")

        logger.info("=" * 60)
        logger.info("  ❌ PIPELINE FAILED")
        if row is not None:
            logger.info(f"  Rows: {row.row_indices} | Title: {row.title}")
        logger.info(f"  Error: {str(e)[:100]}")
        logger.info("=" * 60)
        return 1


def _print_summary(state: StateManager) -> None:
    """Run summary print करो।"""
    s = state.get_summary()
    logger.info("\n📊 OVERALL STATS:")
    logger.info(f"   Total runs:   {s['total_runs']}")
    logger.info(f"   Videos done:  {s['total_done']}")
    logger.info(f"   Failed:       {s['total_failed']}")
    if s['failed_rows']:
        logger.info(f"   Failed rows:  {s['failed_rows']} (manual review karein)")


# ─── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    exit_code = run_pipeline()
    sys.exit(exit_code)
