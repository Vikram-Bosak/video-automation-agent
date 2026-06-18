"""
agents/state_manager.py
───────────────────────
Pipeline का state JSON file में track करता है।
Crash/restart के बाद भी progress बनी रहती है।
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.settings import STATE_FILE

logger = logging.getLogger(__name__)

DEFAULT_STATE = {
    "version": "1.0",
    "last_run_at": None,
    "last_run_status": None,   # "success" | "failed" | "no_pending"
    "total_runs": 0,
    "total_videos_done": 0,
    "total_videos_failed": 0,
    "current_row": None,       # Currently processing row number
    "processed_rows": [],      # Successfully completed rows
    "failed_rows": [],         # Failed rows (manual review के लिए)
    "cookies_saved": False,    # Login cookies cache हैं?
}


class StateManager:
    """
    state.json में pipeline progress save/load करता है।
    Thread-safe नहीं है — single process use मानता है।
    """

    def __init__(self, state_file: Path = STATE_FILE):
        self._file = state_file
        self._state = self._load()
        logger.info(f"📊 State loaded | Total runs: {self._state['total_runs']} | Done: {self._state['total_videos_done']}")

    # ─── Load / Save ──────────────────────────────────────────────────────────

    def _load(self) -> dict:
        """State file load करो, नहीं है तो default create करो।"""
        if self._file.exists():
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    # New keys merge करो (backward compatibility)
                    merged = {**DEFAULT_STATE, **saved}
                    return merged
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"State file corrupt, reset kar rahe hain: {e}")
        return DEFAULT_STATE.copy()

    def _save(self) -> None:
        """State को disk पर save करो।"""
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, ensure_ascii=False)

    # ─── Run Lifecycle ────────────────────────────────────────────────────────

    def begin_run(self, row_index: int) -> None:
        """New run शुरू होने पर call करो।"""
        self._state["total_runs"]    += 1
        self._state["last_run_at"]   = _now()
        self._state["last_run_status"] = "running"
        self._state["current_row"]   = row_index
        self._save()
        logger.info(f"🚀 Run #{self._state['total_runs']} shuru | Row: {row_index}")

    def complete_run(self, row_index: int) -> None:
        """Run successfully complete होने पर।"""
        self._state["last_run_status"]  = "success"
        self._state["total_videos_done"] += 1
        self._state["current_row"]      = None
        if row_index not in self._state["processed_rows"]:
            self._state["processed_rows"].append(row_index)
        # Failed list से हटाओ अगर पहले fail था
        self._state["failed_rows"] = [
            r for r in self._state["failed_rows"] if r != row_index
        ]
        self._save()
        logger.info(f"✅ Run complete | Row {row_index} done | Total done: {self._state['total_videos_done']}")

    def fail_run(self, row_index: Optional[int], reason: str = "") -> None:
        """Run fail होने पर।"""
        self._state["last_run_status"]     = "failed"
        self._state["total_videos_failed"] += 1
        self._state["current_row"]         = None
        if row_index and row_index not in self._state["failed_rows"]:
            self._state["failed_rows"].append(row_index)
        self._save()
        logger.error(f"❌ Run failed | Row {row_index} | Reason: {reason}")

    def no_pending(self) -> None:
        """कोई pending row नहीं मिली।"""
        self._state["last_run_status"] = "no_pending"
        self._state["current_row"]     = None
        self._save()
        logger.info("😴 Koi pending row nahi — is run mein kuch nahi karna")

    # ─── Cookies ──────────────────────────────────────────────────────────────

    def mark_cookies_saved(self) -> None:
        self._state["cookies_saved"] = True
        self._save()

    def is_cookies_saved(self) -> bool:
        return bool(self._state.get("cookies_saved", False))

    def reset_cookies(self) -> None:
        self._state["cookies_saved"] = False
        self._save()

    # ─── Queries ──────────────────────────────────────────────────────────────

    def is_row_processed(self, row_index: int) -> bool:
        """Row पहले से process हो चुकी है?"""
        return row_index in self._state["processed_rows"]

    def get_summary(self) -> dict:
        """Current state का summary।"""
        return {
            "total_runs":   self._state["total_runs"],
            "total_done":   self._state["total_videos_done"],
            "total_failed": self._state["total_videos_failed"],
            "last_run_at":  self._state["last_run_at"],
            "last_status":  self._state["last_run_status"],
            "failed_rows":  self._state["failed_rows"],
        }

    def get_raw(self) -> dict:
        """Full state dict।"""
        return self._state.copy()


# ─── Helper ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
