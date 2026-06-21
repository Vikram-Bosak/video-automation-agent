"""
agents/sheet_reader.py
──────────────────────
Google Sheets से video prompts पढ़ता है और status update करता है।
Google Sheets API v4 + Service Account authentication use करता है।
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config.settings import (
    SHEET_ID, SHEET_NAME, SHEET_RANGE,
    COL_TITLE, COL_PROMPT1, COL_PROMPT2, COL_PROMPT3,
    COL_STATUS, COL_DRIVE_LINK,
    STATUS_PENDING, STATUS_RUNNING, STATUS_DONE, STATUS_FAILED,
    get_google_credentials_dict,
)
from agents.retry_utils import retry_on_failure

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]


@dataclass
class VideoRow:
    """Google Sheet की एक row को represent करता है।"""
    row_index: int          # Sheet में 1-indexed row number
    title: str              # Video का title (file name के लिए)
    prompt1: str            # Prompt 1
    prompt2: str            # Prompt 2
    prompt3: str            # Prompt 3
    status: str = STATUS_PENDING
    drive_links: list[str] = field(default_factory=list)

    def get_prompts(self) -> list[str]:
        """सभी non-empty prompts की list return करता है।"""
        prompts = [self.prompt1, self.prompt2, self.prompt3]
        return [p.strip() for p in prompts if p.strip()]

    def get_safe_title(self) -> str:
        """File system के लिए safe title (special chars remove)।"""
        import re
        safe = re.sub(r'[^\w\s-]', '', self.title)
        safe = re.sub(r'\s+', '_', safe.strip())
        return safe or f"video_row_{self.row_index}"


class SheetReader:
    """Google Sheets read/write operations।"""

    def __init__(self):
        creds_dict = get_google_credentials_dict()
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=SCOPES
        )
        self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        self._sheets  = self._service.spreadsheets()
        logger.info("✅ Google Sheets API initialized")

    # ─── Read ─────────────────────────────────────────────────────────────────

    def get_next_pending_row(self) -> Optional[VideoRow]:
        """
        Sheet में पहली "pending" status वाली row return करता है।
        अगर कोई pending row नहीं है तो None return करता है।
        """
        rows = self._fetch_all_rows()
        for idx, row in enumerate(rows):
            row_num = idx + 2  # Header row skip (1-indexed + header)
            status = self._get_cell(row, COL_STATUS).strip().lower()

            if status == STATUS_PENDING or status == "":
                video_row = self._parse_row(row, row_num)
                if not video_row.title:
                    logger.debug(f"Row {row_num} — title empty, skip karenge")
                    continue

                # Double-check: row abhi bhi pending hai? (race condition guard)
                current_status = self._get_cell(row, COL_STATUS).strip().lower()
                if current_status not in (STATUS_PENDING, ""):
                    logger.info(f"Row {row_num} abhi '{current_status}' hai — skip karenge (another run picked it up)")
                    continue

                logger.info(f"📋 Pending row mili: Row {row_num} | Title: {video_row.title}")
                return video_row

        logger.info("✅ Koi pending row nahi hai sheet mein")
        return None

    def get_all_rows(self) -> list[VideoRow]:
        """सभी rows return करता है (testing के लिए)।"""
        rows = self._fetch_all_rows()
        result = []
        for idx, row in enumerate(rows):
            row_num = idx + 2
            video_row = self._parse_row(row, row_num)
            if video_row.title:
                result.append(video_row)
        return result

    # ─── Write ────────────────────────────────────────────────────────────────

    def mark_running(self, row: VideoRow) -> None:
        """Row को 'running' status दो — दूसरा run duplicate न करे।"""
        self._update_cell(row.row_index, COL_STATUS, STATUS_RUNNING)
        logger.info(f"🔄 Row {row.row_index} → status: running")

    def mark_done(self, row: VideoRow, drive_links: list[str]) -> None:
        """Row को 'done' mark करो और Drive links save करो।"""
        links_str = " | ".join(drive_links)
        self._update_cell(row.row_index, COL_STATUS, STATUS_DONE)
        self._update_cell(row.row_index, COL_DRIVE_LINK, links_str)
        logger.info(f"✅ Row {row.row_index} → status: done | Links: {links_str}")

    def mark_failed(self, row: VideoRow, reason: str = "") -> None:
        """Row को 'failed' mark करो।"""
        self._update_cell(row.row_index, COL_STATUS, f"{STATUS_FAILED}: {reason[:100]}")
        logger.error(f"❌ Row {row.row_index} → status: failed | Reason: {reason}")

    def mark_pending(self, row: VideoRow) -> None:
        """Row को वापस 'pending' करो (retry के लिए)।"""
        self._update_cell(row.row_index, COL_STATUS, STATUS_PENDING)
        logger.info(f"🔁 Row {row.row_index} → status: pending (retry)")

    # ─── Private Helpers ──────────────────────────────────────────────────────

    @retry_on_failure(max_attempts=3, delay_sec=2.0, retryable_exceptions=(HttpError, Exception))
    def _fetch_all_rows(self) -> list[list]:
        """Sheet से सभी rows fetch करता है (header row skip)।"""
        try:
            result = self._sheets.values().get(
                spreadsheetId=SHEET_ID,
                range=f"{SHEET_NAME}!{SHEET_RANGE}",
            ).execute()
            values = result.get("values", [])
            if not values:
                logger.warning("Sheet bilkul empty hai!")
                return []
            return values[1:]  # Header row skip
        except HttpError as e:
            logger.error(f"Sheets API error: {e}")
            raise

    def _parse_row(self, row: list, row_num: int) -> VideoRow:
        """Raw row list को VideoRow object में convert करता है।"""
        return VideoRow(
            row_index = row_num,
            title     = self._get_cell(row, COL_TITLE),
            prompt1   = self._get_cell(row, COL_PROMPT1),
            prompt2   = self._get_cell(row, COL_PROMPT2),
            prompt3   = self._get_cell(row, COL_PROMPT3),
            status    = self._get_cell(row, COL_STATUS),
        )

    def _get_cell(self, row: list, col_idx: int) -> str:
        """Row list से safe cell value निकालता है।"""
        if col_idx < len(row):
            return str(row[col_idx]).strip()
        return ""

    @retry_on_failure(max_attempts=3, delay_sec=2.0, retryable_exceptions=(HttpError, Exception))
    def _update_cell(self, row_num: int, col_idx: int, value: str) -> None:
        """एक specific cell update करता है।"""
        # Column index को letter में convert करो (0→A, 1→B, ...)
        col_letter = chr(ord('A') + col_idx)
        cell_range = f"{SHEET_NAME}!{col_letter}{row_num}"

        try:
            self._sheets.values().update(
                spreadsheetId=SHEET_ID,
                range=cell_range,
                valueInputOption="RAW",
                body={"values": [[value]]},
            ).execute()
        except HttpError as e:
            logger.error(f"Cell update error ({cell_range}): {e}")
            raise
