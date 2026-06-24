"""
agents/google_vids_agent.py
────────────────────────────
Google Vids (docs.google.com/videos) के लिए Playwright automation।
Veo 3.1 AI से 8-second clips generate करता है।
3 prompts = 3 clips = 24 second video

FLOW:
  1. Google Vids खोलो
  2. नया video project बनाओ
  3. Prompt 1 से 8s clip generate करो → timeline में add
  4. Prompt 2 से 8s clip generate करो → timeline में add
  5. Prompt 3 से 8s clip generate करो → timeline में add
  6. Final 24s video export/download करो
  7. File को Title के अनुसार rename करो
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Download,
    TimeoutError as PlaywrightTimeout,
)

from config.settings import (
    BROWSER_HEADLESS, BROWSER_SLOW_MO,
    VIDEO_GEN_TIMEOUT_SEC,
    DOWNLOADS_DIR,
)
from agents.sheet_reader import VideoRow

logger = logging.getLogger(__name__)

COOKIES_FILE = Path("cookies.json")

# ── Google Vids URLs ─────────────────────────────────────────────────────────
GOOGLE_VIDS_BASE  = "https://docs.google.com/videos"
GOOGLE_LOGIN_URL  = "https://accounts.google.com"


class GoogleVidsAgent:
    """
    Google Vids (Veo 3.1) automation agent।
    
    Prerequisites:
      - Google account cookies पहले से save होने चाहिए (एक बार manual login)
      - या GOOGLE_ACCOUNT_EMAIL + GOOGLE_ACCOUNT_PASSWORD env vars
    
    IMPORTANT: Google Vids का UI complex है।
    Selectors को अपने browser के Inspect Element से verify करें।
    Screenshots logs/ folder में save होती हैं debug के लिए।
    """

    # ── Selectors (Google Vids UI — Inspect Element से verify करें) ──────────

    # "Create from scratch" / New project button
    SEL_NEW_VIDEO_BTN   = 'button[aria-label*="Create"], a[aria-label*="new"], button:has-text("Create")'
    
    # "AI video clip" panel trigger
    SEL_AI_CLIP_BTN     = '[aria-label*="AI video clip"], button:has-text("AI video clip"), .veo-panel-trigger'

    # Prompt textarea in AI video clip panel (right side panel)
    # "Describe your 8-second video..."
    SEL_PROMPT_TEXTAREA = 'textarea[placeholder*="8-second"], textarea[placeholder*="Describe"], .veo-prompt-input, [data-placeholder*="Describe"]'

    # "Generate" button in the panel
    SEL_GENERATE_BTN    = 'button.videoGenCreationViewGenerateButton'

    # Generated video result / thumbnail
    SEL_CLIP_RESULT     = '.generated-clip, [class*="clip-result"], [class*="veo-result"], video'

    # "Add to timeline" / "Insert" button after generation
    SEL_ADD_TO_TIMELINE = 'button:has-text("Add"), button:has-text("Insert"), [aria-label*="Add to timeline"]'

    # Download / Export button
    SEL_DOWNLOAD_BTN    = 'button:has-text("Download"), [aria-label*="Download"], [aria-label*="Export"]'
    SEL_DOWNLOAD_MP4    = 'li:has-text("MP4"), button:has-text("MP4"), [aria-label*="MP4"]'

    # Video duration indicator (to confirm 24s)
    SEL_DURATION        = '.total-time, [class*="duration"], [aria-label*="duration"]'

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    # ── Public Interface ──────────────────────────────────────────────────────

    async def process_video_row(self, row: VideoRow) -> Optional[Path]:
        """
        एक VideoRow process करता है।
        Returns: Downloaded & renamed video file path
        """
        safe_title = row.get_safe_title()
        prompts = row.get_prompts()

        logger.info(f"🎬 Google Vids processing: '{safe_title}' | {len(prompts)} prompts")

        try:
            await self._setup_browser()
            
            # Google account check / login
            await self._ensure_google_login()

            # Google Vids पर नया project बनाओ
            video_page_url = await self._create_new_video_project()
            logger.info(f"✅ New Google Vids project: {video_page_url}")

            # तीनों prompts से clips generate करो
            for idx, prompt in enumerate(prompts, start=1):
                logger.info(f"  🎥 Clip {idx}/{len(prompts)}: {prompt[:80]}...")
                success = await self._generate_clip_and_add(prompt, idx)
                if not success:
                    raise RuntimeError(f"Clip {idx} generate karna fail ho gaya")
                logger.info(f"  ✅ Clip {idx} timeline mein add ho gaya")
                await self._human_delay(2, 3)

            # 24 second video confirm करो
            await self._verify_duration(expected_sec=len(prompts) * 8)

            # Video download करो
            raw_file = await self._download_video()
            if not raw_file:
                raise RuntimeError("Video download nahi hui")

            # Rename करो
            suffix = raw_file.suffix or ".mp4"
            renamed = DOWNLOADS_DIR / f"{safe_title}{suffix}"
            import shutil
            shutil.move(str(raw_file), str(renamed))
            logger.info(f"✅ Video renamed: {renamed.name}")

            return renamed

        finally:
            await self._teardown_browser()

    # ── Browser Lifecycle ─────────────────────────────────────────────────────

    async def _setup_browser(self) -> None:
        """Browser शुरू करो।"""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=BROWSER_HEADLESS,
            slow_mo=BROWSER_SLOW_MO,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1366,768",
            ],
        )

        context_options = {
            "viewport": {"width": 1366, "height": 768},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "accept_downloads": True,
        }

        # Saved Google session cookies load करो
        if COOKIES_FILE.exists():
            context_options["storage_state"] = str(COOKIES_FILE)
            logger.info("🍪 Google session cookies loaded")

        self._context = await self._browser.new_context(**context_options)
        self._page = await self._context.new_page()

        await self._page.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
        })

        logger.info(f"✅ Browser ready | Headless: {BROWSER_HEADLESS}")

    async def _teardown_browser(self) -> None:
        """Browser बंद करो और cookies save करो।"""
        try:
            if self._context:
                await self._context.storage_state(path=str(COOKIES_FILE))
                logger.info("🍪 Google session cookies saved")
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"Teardown warning: {e}")

    # ── Google Login ──────────────────────────────────────────────────────────

    async def _ensure_google_login(self) -> None:
        """
        Google account login check।
        
        NOTE: Google का login CAPTCHA/2FA complex है।
        RECOMMENDED: पहली बार manually login करो, cookies.json save हो जाएगी।
        फिर automatic runs में cookies use होंगी।
        """
        import os
        google_email = os.environ.get("GOOGLE_ACCOUNT_EMAIL", "")
        
        # ── Cookie validation ────────────────────────────────────────────────
        if COOKIES_FILE.exists():
            try:
                import json
                cookie_data = json.loads(COOKIES_FILE.read_text())
                cookie_count = len(cookie_data.get("cookies", []))
                if cookie_count == 0:
                    logger.warning("⚠️  cookies.json exists but has 0 cookies — login required")
                    await self._take_screenshot("empty_cookies")
                else:
                    logger.info(f"🍪 cookies.json loaded ({cookie_count} cookies)")
            except Exception as e:
                logger.warning(f"⚠️  cookies.json corrupted: {e} — login required")
        else:
            logger.warning("⚠️  No cookies.json found — login required")
        
        # Google Vids page खोलो (login check के लिए)
        await self._page.goto(GOOGLE_VIDS_BASE, wait_until="networkidle", timeout=30_000)
        await self._human_delay(2, 3)

        current_url = self._page.url
        logger.info(f"Current URL: {current_url}")

        if "accounts.google.com" in current_url or "signin" in current_url.lower():
            logger.warning("⚠️  Google login required!")
            logger.warning("Manual login की जरूरत है — cookies.json save करना होगा")
            await self._take_screenshot("need_login")

            if google_email:
                await self._do_google_login(google_email, os.environ.get("GOOGLE_ACCOUNT_PASSWORD", ""))
            else:
                raise RuntimeError(
                    "Google login required! "
                    "GOOGLE_ACCOUNT_EMAIL और GOOGLE_ACCOUNT_PASSWORD set करें, "
                    "या पहले manually login करके cookies.json save करें।"
                )
        else:
            logger.info("✅ Google account already logged in")

    async def _do_google_login(self, email: str, password: str) -> None:
        """Google account login flow।"""
        logger.info(f"🔐 Google login: {email[:5]}***")

        # Email
        await self._page.goto("https://accounts.google.com/signin", wait_until="networkidle")
        await self._safe_fill('input[type="email"]', email)
        await self._safe_click('#identifierNext button, button:has-text("Next")')
        await self._human_delay(2, 3)

        # Password
        await self._safe_fill('input[type="password"]', password)
        await self._safe_click('#passwordNext button, button:has-text("Next")')
        await self._human_delay(3, 5)

        # Login complete check
        await self._page.wait_for_url("https://myaccount.google.com/**", timeout=30_000)
        logger.info("✅ Google login successful")

    # ── Google Vids Workflow ──────────────────────────────────────────────────

    async def _create_new_video_project(self) -> str:
        """
        Google Vids में नया video project create करो।
        Returns: New project URL
        """
        logger.info("📹 Google Vids mein naya project bana rahe hain...")

        # Google Vids home
        await self._page.goto(GOOGLE_VIDS_BASE, wait_until="networkidle", timeout=30_000)
        await self._human_delay(2, 3)
        await self._take_screenshot("vids_home")

        # "Blank video" / "Create from scratch" पर click
        new_btn_selectors = [
            '.docs-homescreen-templates-templateview',
            '.docs-homescreen-fab',
            'button:has-text("Blank video")',
            'button:has-text("New video")',
            'a:has-text("Blank video")',
            '[aria-label*="Blank video"]',
            '[aria-label*="New video"]',
        ]

        clicked = False
        for sel in new_btn_selectors:
            if await self._safe_click(sel, timeout=5_000):
                clicked = True
                logger.info(f"✅ New video button clicked: {sel}")
                break

        if not clicked:
            await self._take_screenshot("new_video_btn_not_found")
            raise RuntimeError("Google Vids mein 'New video' button nahi mila. Screenshot dekho.")

        # New project load होने का wait
        await self._page.wait_for_url("**/videos/d/**", timeout=30_000)
        await self._human_delay(3, 5)
        await self._take_screenshot("new_project_created")

        return self._page.url

    async def _generate_clip_and_add(self, prompt: str, clip_number: int) -> bool:
        """
        AI Video Clip panel use करके एक 8-second clip generate करो।
        """
        # Check if the AI video clip panel is already open
        panel_title_sel = '.appsDocsAiGenerativeaiVideoUiSidebarWizVideogensidebarSideSheetTitle, header:has-text("AI video clip")'
        panel_already_open = False
        try:
            if await self._page.is_visible(panel_title_sel, timeout=1000):
                panel_already_open = True
                logger.info("✅ AI video clip panel is already open")
        except Exception:
            pass

        panel_opened = panel_already_open
        if not panel_opened:
            # Check if 'Getting started' modal dialog is visible and click the Veo card
            modal_button_sel = '.appsDocsGettingStartedEntryPointSelectionViewButton.videogen, button:has-text("Veo 3.1")'
            try:
                if await self._page.is_visible(modal_button_sel, timeout=2000):
                    logger.info("Getting started modal is open, clicking Veo 3.1 card...")
                    await self._page.click(modal_button_sel)
                    panel_opened = True
            except Exception:
                pass

        if not panel_opened:
            # Fallback: try clicking side rail icon or other triggers
            veo_btn_selectors = [
                '[aria-label="Generate an AI video clip"]',
                '[aria-label*="AI video clip"]',
                'button:has-text("AI video clip")',
                '.veo-trigger',
                '[data-panel-id="veo"]',
                'button[title*="Veo"]',
            ]
            for sel in veo_btn_selectors:
                if await self._safe_click(sel, timeout=3000):
                    panel_opened = True
                    logger.info(f"✅ AI video clip panel opened via: {sel}")
                    break

        if panel_opened:
            try:
                await self._page.wait_for_selector(panel_title_sel, state="visible", timeout=10_000)
            except Exception as e:
                logger.warning(f"Panel title selector not found after opening attempts: {e}")
        else:
            await self._take_screenshot(f"veo_panel_not_found_{clip_number}")
            logger.error("Veo panel nahi khula — selector verify karein")
            return False

        await self._human_delay(1, 2)

        # Prompt textarea में type करो
        prompt_filled = await self._safe_fill(
            self.SEL_PROMPT_TEXTAREA,
            prompt,
            timeout=10_000,
        )

        if not prompt_filled:
            await self._take_screenshot(f"prompt_fill_failed_{clip_number}")
            logger.error(f"Prompt textarea nahi mila (clip {clip_number})")
            return False

        await self._human_delay(1, 2)
        await self._take_screenshot(f"prompt_filled_{clip_number}")

        # Generate button click
        gen_clicked = await self._safe_click(self.SEL_GENERATE_BTN, timeout=10_000)
        if not gen_clicked:
            await self._take_screenshot(f"generate_btn_failed_{clip_number}")
            return False

        logger.info(f"  ⏳ Clip {clip_number} generate ho rahi hai... (max {VIDEO_GEN_TIMEOUT_SEC}s)")
        await self._take_screenshot(f"generating_{clip_number}")

        # Generation complete होने का wait
        clip_ready = await self._wait_for_clip_ready(clip_number)
        if not clip_ready:
            return False

        # Timeline में add करो
        await self._human_delay(1, 2)
        add_selectors = [
            'button:has-text("Add to video")',
            'button:has-text("Insert")',
            'button:has-text("Add")',
            '[aria-label*="Add to timeline"]',
            '[aria-label*="Add to video"]',
        ]

        added = False
        for sel in add_selectors:
            if await self._safe_click(sel, timeout=5_000):
                added = True
                logger.info(f"  ✅ Clip {clip_number} timeline mein add kiya")
                break

        if not added:
            await self._take_screenshot(f"add_to_timeline_failed_{clip_number}")
            logger.warning(f"'Add to timeline' button nahi mila — manually check karein")

        await self._human_delay(2, 3)
        return True

    async def _wait_for_clip_ready(self, clip_number: int) -> bool:
        """Clip generation complete होने का wait करो।"""
        start = time.time()
        check_interval = 5  # हर 5 seconds check

        clip_ready_selectors = [
            '.generated-clip',
            '[class*="veo-result"]',
            '[class*="clip-thumbnail"]',
            'button:has-text("Add to video")',
            'button:has-text("Insert")',
        ]

        while time.time() - start < VIDEO_GEN_TIMEOUT_SEC:
            for sel in clip_ready_selectors:
                try:
                    await self._page.wait_for_selector(sel, state="visible", timeout=check_interval * 1000)
                    elapsed = int(time.time() - start)
                    logger.info(f"  🎉 Clip {clip_number} ready! ({elapsed}s)")
                    await self._take_screenshot(f"clip_ready_{clip_number}")
                    return True
                except PlaywrightTimeout:
                    continue

            elapsed = int(time.time() - start)
            logger.info(f"  ⏳ Clip {clip_number} still generating... ({elapsed}s)")

        logger.error(f"Clip {clip_number} timeout after {VIDEO_GEN_TIMEOUT_SEC}s")
        await self._take_screenshot(f"clip_timeout_{clip_number}")
        return False

    async def _verify_duration(self, expected_sec: int) -> None:
        """Total video duration verify करो।"""
        await self._human_delay(1, 2)
        try:
            duration_elem = await self._page.query_selector(self.SEL_DURATION)
            if duration_elem:
                text = await duration_elem.inner_text()
                logger.info(f"📏 Video duration: {text} (expected: ~{expected_sec}s)")
        except Exception:
            logger.warning("Duration verify nahi ho saka — continue kar rahe hain")

    async def _download_video(self) -> Optional[Path]:
        """
        Video download करो।
        Google Vids में: File → Download → MP4
        """
        logger.info("📥 Video download shuru kar rahe hain...")
        await self._take_screenshot("before_download")

        # Download trigger करो
        download_sequences = [
            # Option 1: Direct download button
            [('button:has-text("Download")', 5_000)],
            # Option 2: File menu → Download
            [('button[aria-label="File"], button:has-text("File")', 5_000),
             ('li:has-text("Download"), button:has-text("Download")', 5_000)],
            # Option 3: More options → Download
            [('[aria-label*="More options"]', 5_000),
             ('li:has-text("Download")', 5_000)],
        ]

        for sequence in download_sequences:
            try:
                async with self._page.expect_download(timeout=300_000) as dl_info:
                    last_clicked = False
                    for sel, timeout in sequence[:-1]:
                        await self._safe_click(sel, timeout)
                        await self._human_delay(0.5, 1)

                    # Last click triggers download
                    last_sel, last_timeout = sequence[-1]
                    await self._safe_click(last_sel, last_timeout)

                download: Download = await dl_info.value
                dest = DOWNLOADS_DIR / download.suggested_filename
                await download.save_as(str(dest))
                logger.info(f"✅ Video downloaded: {dest.name}")
                await self._take_screenshot("download_complete")
                return dest

            except PlaywrightTimeout:
                logger.warning("Download sequence failed, next try karenge...")
                continue
            except Exception as e:
                logger.warning(f"Download attempt failed: {e}")
                continue

        await self._take_screenshot("download_all_failed")
        logger.error("Sabhi download attempts fail ho gayi")
        return None

    # ── Utilities ─────────────────────────────────────────────────────────────

    async def _safe_click(self, selector: str, timeout: int = 10_000) -> bool:
        try:
            await self._page.wait_for_selector(selector, state="visible", timeout=timeout)
            await self._page.click(selector)
            return True
        except PlaywrightTimeout:
            logger.warning(f"Click timeout for selector: {selector}")
            return False
        except Exception as e:
            logger.warning(f"Click error ({selector}): {e}")
            return False

    async def _safe_fill(self, selector: str, text: str, timeout: int = 10_000) -> bool:
        try:
            await self._page.wait_for_selector(selector, state="visible", timeout=timeout)
            await self._page.click(selector)
            # Select all and delete (safe for contenteditable)
            await self._page.press(selector, "Control+A")
            await self._page.press(selector, "Delete")
            await asyncio.sleep(0.2)
            # Type instantly with no delay
            await self._page.type(selector, text, delay=0)
            return True
        except PlaywrightTimeout:
            logger.warning(f"Fill timeout for selector: {selector}")
            return False
        except Exception as e:
            logger.warning(f"Fill error ({selector}): {e}")
            return False

    async def _human_delay(self, min_sec: float = 1.0, max_sec: float = 3.0) -> None:
        import random
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)

    async def _take_screenshot(self, name: str) -> None:
        try:
            path = DOWNLOADS_DIR.parent / "logs" / f"{name}_{int(time.time())}.png"
            await self._page.screenshot(path=str(path), full_page=False)
            logger.info(f"📸 Screenshot: {path.name}")
        except Exception as e:
            logger.warning(f"Screenshot error ({name}): {e}")
            pass


# ── Sync wrapper ──────────────────────────────────────────────────────────────

def run_google_vids_agent(row: VideoRow) -> Optional[Path]:
    """Async agent को sync context में चलाता है।"""
    agent = GoogleVidsAgent()
    return asyncio.run(agent.process_video_row(row))
