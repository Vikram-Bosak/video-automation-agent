"""
agents/drive_uploader.py
────────────────────────
Google Drive API v3 से files upload करता है।
Service Account authentication use करता है।
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from config.settings import DRIVE_FOLDER_ID, get_google_credentials_dict
from agents.retry_utils import retry_on_failure

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",   # Only files created by this app
]

# MIME types
MIME_VIDEO   = "video/mp4"
MIME_UNKNOWN = "application/octet-stream"


class DriveUploader:
    """Google Drive में files upload करता है।"""

    def __init__(self):
        creds_dict = get_google_credentials_dict()
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=SCOPES
        )
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        logger.info("✅ Google Drive API initialized")

    # ─── Public Interface ─────────────────────────────────────────────────────

    @retry_on_failure(max_attempts=3, delay_sec=3.0, retryable_exceptions=(HttpError, Exception))
    def upload_video(self, file_path: Path, folder_id: Optional[str] = None) -> Optional[str]:
        """
        Video file Google Drive में upload करता है।
        Returns: Google Drive file URL, या None अगर fail हो।
        """
        folder = folder_id or DRIVE_FOLDER_ID
        if not folder:
            raise ValueError("DRIVE_FOLDER_ID set nahi hai! .env या GitHub Secrets check karein.")

        if not file_path.exists():
            logger.error(f"File exist nahi karti: {file_path}")
            return None

        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        logger.info(f"📤 Uploading: {file_path.name} ({file_size_mb:.1f} MB) → Drive")

        try:
            mime_type = self._get_mime_type(file_path)

            file_metadata = {
                "name":    file_path.name,
                "parents": [folder],
            }

            media = MediaFileUpload(
                str(file_path),
                mimetype=mime_type,
                resumable=True,   # Large files के लिए resumable upload
                chunksize=5 * 1024 * 1024,  # 5 MB chunks
            )

            file = self._service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, name, webViewLink, webContentLink",
            ).execute()

            drive_url  = file.get("webViewLink", "")
            file_id    = file.get("id", "")

            logger.info(f"✅ Upload done: {file_path.name} | ID: {file_id}")
            logger.info(f"   🔗 Drive URL: {drive_url}")
            return drive_url

        except HttpError as e:
            logger.error(f"Drive upload error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected upload error: {e}")
            return None

    def upload_multiple(self, files: list[Path], folder_id: Optional[str] = None) -> list[str]:
        """
        Multiple files upload करो।
        Returns: Successfully uploaded files की Drive URLs।
        """
        links = []
        for f in files:
            url = self.upload_video(f, folder_id)
            if url:
                links.append(url)
            else:
                logger.warning(f"⚠️ Upload skip: {f.name}")
        return links

    def ensure_folder_exists(self, folder_name: str, parent_id: Optional[str] = None) -> str:
        """
        नया folder बनाओ (अगर पहले से नहीं है)।
        Returns: Folder ID
        """
        # Check if folder exists
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"

        result = self._service.files().list(
            q=query, fields="files(id, name)"
        ).execute()

        files = result.get("files", [])
        if files:
            fid = files[0]["id"]
            logger.info(f"📁 Folder already exists: '{folder_name}' | ID: {fid}")
            return fid

        # Create new folder
        meta = {
            "name":     folder_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            meta["parents"] = [parent_id]

        folder = self._service.files().create(
            body=meta, fields="id"
        ).execute()
        fid = folder.get("id")
        logger.info(f"📁 Folder created: '{folder_name}' | ID: {fid}")
        return fid

    def delete_file_after_upload(self, file_path: Path) -> None:
        """Upload के बाद local file delete करो (disk space बचाओ)।"""
        try:
            file_path.unlink()
            logger.info(f"🗑️  Local file deleted: {file_path.name}")
        except Exception as e:
            logger.warning(f"Local file delete failed: {e}")

    # ─── Private Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _get_mime_type(file_path: Path) -> str:
        """File extension से MIME type detect करो।"""
        ext = file_path.suffix.lower()
        mime_map = {
            ".mp4":  "video/mp4",
            ".mov":  "video/quicktime",
            ".avi":  "video/x-msvideo",
            ".mkv":  "video/x-matroska",
            ".webm": "video/webm",
        }
        return mime_map.get(ext, MIME_UNKNOWN)
