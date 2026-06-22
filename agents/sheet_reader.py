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
    COL_DAY, COL_CATEGORY, COL_TITLE, COL_TOPIC,
    COL_SCENE, COL_SCENE_LABEL, COL_PROMPT,
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
    """Google Sheet की एक grouped rows (1 day/video = 3 rows) को represent करता है।"""
    row_indices: list[int]  # Sheet में 1-indexed row numbers (typically 3 rows)
    row_index: int          # For backward compatibility (maps to row_indices[0])
    title: str              # Video का title (file name के लिए)
    day: str                # Day number
    prompt1: str            # Prompt for Scene 1
    prompt2: str            # Prompt for Scene 2
    prompt3: str            # Prompt for Scene 3
    status: str = STATUS_PENDING
    drive_links: list[str] = field(default_factory=list)

    def get_prompts(self) -> list[str]:
        """सभी non-empty prompts की list return करता है।"""
        prompts = [self.prompt1, self.prompt2, self.prompt3]
        return [p.strip() for p in prompts if p.strip()]

    def get_safe_title(self) -> str:
        """File system के लिए safe title (special chars remove)।"""
        import re
        # Remove characters that are not word characters, spaces, or hyphens
        safe = re.sub(r'[^\w\s-]', '', self.title)
        safe = re.sub(r'\s+', '_', safe.strip())
        return safe or f"video_day_{self.day or self.row_index}"


class SheetReader:
    """Google Sheets read/write operations (KidoBum grouped schema)।"""

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
        Sheet में पहली "pending" status वाली row group (Day/Title) return करता है।
        अगर कोई pending group नहीं है तो None return करता है।
        """
        rows = self._fetch_all_rows()
        # Group consecutive rows by Day / Title
        groups: dict[str, list[tuple[int, list]]] = {}
        for idx, row in enumerate(rows):
            row_num = idx + 2  # Header row is row 1
            day = self._get_cell(row, COL_DAY).strip()
            title = self._get_cell(row, COL_TITLE).strip()
            
            if not title:
                continue
                
            group_key = day if day else title
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append((row_num, row))

        # Check each group for pending status
        for group_key, group_items in groups.items():
            has_pending = False
            for row_num, row_data in group_items:
                status = self._get_cell(row_data, COL_STATUS).strip().lower()
                # Empty status or "pending" or containing "failed" indicates it needs processing
                if status == STATUS_PENDING or status == "" or "failed" in status:
                    has_pending = True
                    break
            
            if has_pending:
                # Group found! Let's sort by Scene index
                sorted_items = sorted(group_items, key=lambda x: self._get_scene_num(x[1]))
                first_row_num, first_row = sorted_items[0]
                
                title = self._get_cell(first_row, COL_TITLE).strip()
                day = self._get_cell(first_row, COL_DAY).strip()
                
                prompt1 = ""
                prompt2 = ""
                prompt3 = ""
                row_indices = []
                
                for row_num, row_data in sorted_items:
                    row_indices.append(row_num)
                    scene_str = self._get_cell(row_data, COL_SCENE).strip()
                    prompt_text = self._get_cell(row_data, COL_PROMPT).strip()
                    
                    if scene_str == "1":
                        prompt1 = prompt_text
                    elif scene_str == "2":
                        prompt2 = prompt_text
                    elif scene_str == "3":
                        prompt3 = prompt_text
                    else:
                        # Fallback ordering
                        if not prompt1:
                            prompt1 = prompt_text
                        elif not prompt2:
                            prompt2 = prompt_text
                        elif not prompt3:
                            prompt3 = prompt_text

                # Double check race condition: ensure status is still pending/empty/failed
                # (fetch latest status of first row just to be sure)
                video_row = VideoRow(
                    row_indices = row_indices,
                    row_index = row_indices[0],
                    title = title,
                    day = day,
                    prompt1 = prompt1,
                    prompt2 = prompt2,
                    prompt3 = prompt3,
                    status = STATUS_PENDING
                )
                logger.info(f"📋 Pending row group found: Day {day} | Title: '{title}' | Rows: {row_indices}")
                return video_row

        logger.info("✅ Sheet mein koi pending group nahi hai")
        return None

    def get_all_rows(self) -> list[VideoRow]:
        """सभी grouped rows return करता है (testing के लिए)।"""
        rows = self._fetch_all_rows()
        groups: dict[str, list[tuple[int, list]]] = {}
        for idx, row in enumerate(rows):
            row_num = idx + 2
            day = self._get_cell(row, COL_DAY).strip()
            title = self._get_cell(row, COL_TITLE).strip()
            
            if not title:
                continue
                
            group_key = day if day else title
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append((row_num, row))

        result = []
        for group_key, group_items in groups.items():
            sorted_items = sorted(group_items, key=lambda x: self._get_scene_num(x[1]))
            first_row_num, first_row = sorted_items[0]
            
            title = self._get_cell(first_row, COL_TITLE).strip()
            day = self._get_cell(first_row, COL_DAY).strip()
            
            prompt1 = ""
            prompt2 = ""
            prompt3 = ""
            row_indices = []
            
            for row_num, row_data in sorted_items:
                row_indices.append(row_num)
                scene_str = self._get_cell(row_data, COL_SCENE).strip()
                prompt_text = self._get_cell(row_data, COL_PROMPT).strip()
                
                if scene_str == "1":
                    prompt1 = prompt_text
                elif scene_str == "2":
                    prompt2 = prompt_text
                elif scene_str == "3":
                    prompt3 = prompt_text
                else:
                    if not prompt1:
                        prompt1 = prompt_text
                    elif not prompt2:
                        prompt2 = prompt_text
                    elif not prompt3:
                        prompt3 = prompt_text
                        
            video_row = VideoRow(
                row_indices = row_indices,
                row_index = row_indices[0],
                title = title,
                day = day,
                prompt1 = prompt1,
                prompt2 = prompt2,
                prompt3 = prompt3,
                status = self._get_cell(first_row, COL_STATUS).strip()
            )
            result.append(video_row)
        return result

    # ─── Write ────────────────────────────────────────────────────────────────

    def mark_running(self, row: VideoRow) -> None:
        """Row group को 'running' status दो — दूसरा run duplicate न करे।"""
        for r_idx in row.row_indices:
            self._update_cell(r_idx, COL_STATUS, STATUS_RUNNING)
        logger.info(f"🔄 Row group {row.row_indices} → status: running")

    def mark_done(self, row: VideoRow, drive_links: list[str]) -> None:
        """Row group को 'done' mark करो और Drive links save करो।"""
        for idx, r_idx in enumerate(row.row_indices):
            self._update_cell(r_idx, COL_STATUS, STATUS_DONE)
            # If there's 1 link, populate it for all scenes in the group (e.g. Google Vids combined mp4)
            # If there are 3 links, populate corresponding link for each scene (e.g. Kling AI parts)
            if len(drive_links) == 1:
                self._update_cell(r_idx, COL_DRIVE_LINK, drive_links[0])
            elif idx < len(drive_links):
                self._update_cell(r_idx, COL_DRIVE_LINK, drive_links[idx])
        logger.info(f"✅ Row group {row.row_indices} → status: done | Links: {drive_links}")

    def mark_failed(self, row: VideoRow, reason: str = "") -> None:
        """Row group को 'failed' mark करो।"""
        for r_idx in row.row_indices:
            self._update_cell(r_idx, COL_STATUS, f"{STATUS_FAILED}: {reason[:100]}")
        logger.error(f"❌ Row group {row.row_indices} → status: failed | Reason: {reason}")

    def mark_pending(self, row: VideoRow) -> None:
        """Row group को वापस 'pending' करो (retry के लिए)।"""
        for r_idx in row.row_indices:
            self._update_cell(r_idx, COL_STATUS, STATUS_PENDING)
        logger.info(f"🔁 Row group {row.row_indices} → status: pending (retry)")

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

    def _get_cell(self, row: list, col_idx: int) -> str:
        """Row list से safe cell value निकालता है।"""
        if col_idx < len(row):
            return str(row[col_idx]).strip()
        return ""

    def _get_scene_num(self, row: list) -> int:
        """Scene column से integer scene value निकालता है (default to 0)।"""
        scene_str = self._get_cell(row, COL_SCENE)
        try:
            return int(scene_str)
        except ValueError:
            return 0

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
