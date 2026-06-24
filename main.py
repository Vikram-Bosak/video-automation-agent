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

NOTE: अब यह multiple videos per run process करता है
      (MAX_VIDEOS_PER_RUN setting के अनुसार)
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")


from config.settings import (
    LOGS_DIR, LOG_LEVEL, WEBSITE_URL,
    MAX_VIDEOS_PER_RUN, validate_config,
)
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


# ─── Health Check ──────────────────────────────────────────────────────────────

def run_health_check() -> bool:
    """
    Startup पर config validate करो।
    Returns: True if all OK, False if critical errors found
    """
    logger.info("\n🔍 HEALTH CHECK: Config validate kar rahe hain...")

    errors = validate_config()

    if not errors:
        logger.info("✅ Health check passed — sab kuch set hai!")
        return True

    logger.warning(f"⚠️  Health check mein {len(errors)} issue(s) mile:")
    for i, err in enumerate(errors, 1):
        logger.warning(f"   {i}. {err}")

    # Critical errors jo pipeline rok sakte hain
    critical = [e for e in errors if "GOOGLE_CREDENTIALS" in e or "SHEET_ID" in e or "DRIVE_FOLDER_ID" in e]
    if critical:
        logger.error("\n❌ CRITICAL ERRORS — Pipeline band kar rahe hain:")
        for e in critical:
            logger.error(f"   🔴 {e}")
        return False

    logger.info("\n⚠️  Non-critical issues hain — pipeline chalega lekin issues aa sakte hain.")
    return True


# ─── Process Single Video Row ──────────────────────────────────────────────────

def process_single_video(row: VideoRow, sheet: SheetReader, drive: DriveUploader,
                          state: StateManager) -> bool:
    """
    एक VideoRow process करता है।
    Returns: True if success, False if failed
    """
    logger.info(f"\n{'─' * 60}")
    logger.info(f"🎬 Processing: '{row.title}' | Rows: {row.row_indices}")
    logger.info(f"   Prompts: {len(row.get_prompts())}")

    try:
        # Row को "running" mark करो
        sheet.mark_running(row)
        state.begin_run(row.row_index)

        downloaded_files: list[Path] = []
        drive_links: list[str] = []

        # Browser agent चलाओ
        url = WEBSITE_URL.lower()
        if "docs.google.com/videos" in url or "google.com/videos" in url or "vids" in url:
            logger.info("🌐 Using Google Vids Agent")
            downloaded_file = run_google_vids_agent(row)
            if not downloaded_file:
                raise RuntimeError(f"Koi video download nahi hua for rows {row.row_indices}")
            downloaded_files = [downloaded_file]
        else:
            logger.info(f"🌐 Using Browser Agent for: {WEBSITE_URL}")
            from agents.browser_agent import run_browser_agent
            downloaded_files = run_browser_agent(row)
            if not downloaded_files:
                raise RuntimeError(f"Koi video download nahi hua for rows {row.row_indices}")

        logger.info(f"✅ {len(downloaded_files)} video(s) download hui:")
        for f in downloaded_files:
            size_mb = f.stat().st_size / (1024 * 1024)
            logger.info(f"   • {f.name} ({size_mb:.1f} MB)")

        # Google Drive पर upload
        logger.info("☁️  Google Drive upload shuru...")
        drive_links = drive.upload_multiple(downloaded_files)

        if not drive_links:
            raise RuntimeError("Drive upload fail ho gayi — koi file upload nahi hui")

        logger.info(f"✅ {len(drive_links)} file(s) Drive mein upload:")
        for link in drive_links:
            logger.info(f"   🔗 {link}")

        # Sheet में "done" mark करो
        sheet.mark_done(row, drive_links)
        state.complete_run(row.row_index)

        # Local files cleanup
        for f in downloaded_files:
            drive.delete_file_after_upload(f)

        logger.info(f"✅ COMPLETE: '{row.title}' | Links: {len(drive_links)}")
        return True

    except Exception as e:
        logger.error(f"❌ FAILED: '{row.title}' — {e}", exc_info=True)

        try:
            sheet.mark_failed(row, str(e))
        except Exception as sheet_err:
            logger.error(f"Sheet mark_failed error: {sheet_err}")

        try:
            state.fail_run(row.row_index, str(e))
        except Exception as state_err:
            logger.error(f"State fail_run error: {state_err}")

        return False


# ─── Main Pipeline ─────────────────────────────────────────────────────────────

def run_pipeline() -> int:
    """
    Main pipeline चलाता है।
    Returns: Exit code (0 = success, 1 = error, 2 = no pending rows)
    """
    setup_logging()

    logger.info("=" * 60)
    logger.info("  🚀 VIDEO AUTOMATION PIPELINE STARTING")
    logger.info(f"  📊 Max videos per run: {MAX_VIDEOS_PER_RUN}")
    logger.info("=" * 60)

    # ── Health Check ──────────────────────────────────────────────────────────
    if not run_health_check():
        return 1

    state = None
    sheet = None
    drive = None

    try:
        state   = StateManager()
        sheet   = SheetReader()
        drive   = DriveUploader()

        # ── Stuck Row Recovery ────────────────────────────────────────────────
        recovered = sheet.recover_stuck_rows()
        if recovered > 0:
            logger.info(f"🔄 {recovered} stuck row(s) recovered → pending status")

        # ── Process Multiple Videos ───────────────────────────────────────────
        total_processed = 0
        total_success = 0
        total_failed = 0

        while total_processed < MAX_VIDEOS_PER_RUN:
            logger.info(f"\n📋 Looking for pending row ({total_processed + 1}/{MAX_VIDEOS_PER_RUN})...")

            row = sheet.get_next_pending_row()
            if row is None:
                if total_processed == 0:
                    logger.info("✅ Koi pending row nahi — pipeline band ho rahi hai.")
                    state.no_pending()
                    return 2
                else:
                    logger.info(f"✅ Aur koi pending row nahi. Processed: {total_processed}")
                    break

            success = process_single_video(row, sheet, drive, state)
            total_processed += 1

            if success:
                total_success += 1
                logger.info(f"✅ Video {total_processed}/{MAX_VIDEOS_PER_RUN} SUCCESS")
            else:
                total_failed += 1
                logger.warning(f"⚠️  Video {total_processed}/{MAX_VIDEOS_PER_RUN} FAILED")

            # Next video ke liye thoda wait
            if total_processed < MAX_VIDEOS_PER_RUN:
                logger.info("⏳ Next video ke liye 5s wait...")
                time.sleep(5)

        # ── Final Summary ─────────────────────────────────────────────────────
        logger.info("\n" + "=" * 60)
        logger.info("  📊 PIPELINE SESSION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"  Total processed: {total_processed}")
        logger.info(f"  ✅ Success:      {total_success}")
        logger.info(f"  ❌ Failed:       {total_failed}")
        logger.info("=" * 60)

        _print_summary(state)
        return 0 if total_failed == 0 else 1

    except Exception as e:
        logger.error(f"\n❌ PIPELINE ERROR: {e}", exc_info=True)
        logger.info("=" * 60)
        logger.info("  ❌ PIPELINE FAILED")
        logger.info(f"  Error: {str(e)[:200]}")
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
