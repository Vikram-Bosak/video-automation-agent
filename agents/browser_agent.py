"""
agents/browser_agent.py
───────────────────────
Playwright (Python) से AI video website को automate करता है।

ARCHITECTURE:
  BrowserAgent (base class)
    └── KlingAIAgent     ← Kling AI के लिए
    └── RunwayAgent      ← Runway ML के लिए
    └── PikaAgent        ← Pika Labs के लिए
    └── CustomAgent      ← Custom website के लिए

अपनी website के लिए सही subclass use करें।
Selectors अपनी website के inspect element से verify करें।
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from abc import ABC, abstractmethod
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
    WEBSITE_URL, WEBSITE_EMAIL, WEBSITE_PASSWORD,
    DOWNLOADS_DIR,
)
from agents.sheet_reader import VideoRow

logger = logging.getLogger(__name__)

COOKIES_FILE = Path("cookies.json")   # Login session save करने के लिए


# ══════════════════════════════════════════════════════════════════════════════
# BASE CLASS
# ══════════════════════════════════════════════════════════════════════════════

class BrowserAgent(ABC):
    """
    Base browser automation agent।
    Subclass में website-specific methods implement करें।
    """

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    # ─── Public Interface ─────────────────────────────────────────────────────

    async def process_video_row(self, row: VideoRow) -> list[Path]:
        """
        एक VideoRow process करता है।
        Returns: Downloaded video files की list (renamed)
        """
        downloaded_files = []
        prompts = row.get_prompts()
        safe_title = row.get_safe_title()

        logger.info(f"🎬 Processing row: '{safe_title}' | {len(prompts)} prompts")

        try:
            await self._setup_browser()
            await self._ensure_logged_in()

            for idx, prompt in enumerate(prompts, start=1):
                logger.info(f"  📝 Prompt {idx}/{len(prompts)}: {prompt[:60]}...")

                # Video generate करो
                raw_file = await self._generate_and_download(prompt, idx)

                if raw_file:
                    # File rename करो: Title_part1.mp4
                    suffix = raw_file.suffix or ".mp4"
                    new_name = f"{safe_title}_part{idx}{suffix}"
                    renamed  = DOWNLOADS_DIR / new_name
                    shutil.move(str(raw_file), str(renamed))
                    downloaded_files.append(renamed)
                    logger.info(f"  ✅ Downloaded & renamed: {new_name}")
                else:
                    logger.error(f"  ❌ Prompt {idx} ka video download nahi hua")

        finally:
            await self._teardown_browser()

        return downloaded_files

    # ─── Browser Lifecycle ────────────────────────────────────────────────────

    async def _setup_browser(self) -> None:
        """Playwright browser शुरू करो।"""
        self._playwright = await async_playwright().start()
        self._browser    = await self._playwright.chromium.launch(
            headless  = BROWSER_HEADLESS,
            slow_mo   = BROWSER_SLOW_MO,
            args      = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",       # GitHub Actions के लिए
                "--disable-blink-features=AutomationControlled",  # Bot detection से बचाव
            ],
        )

        # Context बनाओ (cookies, viewport, user-agent)
        context_options = {
            "viewport": {"width": 1366, "height": 768},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "accept_downloads": True,
        }

        # Saved cookies load करो (login skip के लिए)
        if COOKIES_FILE.exists():
            context_options["storage_state"] = str(COOKIES_FILE)
            logger.info("🍪 Saved cookies load kiye")

        self._context = await self._browser.new_context(**context_options)
        self._page    = await self._context.new_page()

        # Extra headers (bot detection से बचाव)
        await self._page.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
        })

        logger.info(f"✅ Browser ready | Headless: {BROWSER_HEADLESS}")

    async def _teardown_browser(self) -> None:
        """Browser बंद करो।"""
        try:
            if self._context:
                # Cookies save करो अगले run के लिए
                await self._context.storage_state(path=str(COOKIES_FILE))
                logger.info("🍪 Cookies save kiye")
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"Browser teardown warning: {e}")

    async def _ensure_logged_in(self) -> None:
        """
        Login check करो। अगर session expire हो गई है तो login करो।
        """
        await self._page.goto(WEBSITE_URL, wait_until="networkidle", timeout=30_000)

        if await self._is_logged_in():
            logger.info("✅ Already logged in (cookies valid)")
        else:
            logger.info("🔐 Login karna pad raha hai...")
            await self._do_login()

    # ─── Abstract Methods (Subclass में implement करें) ─────────────────────

    @abstractmethod
    async def _is_logged_in(self) -> bool:
        """
        Check करो कि current page पर user logged in है।
        Example: किसी logged-in-only element का check।
        """

    @abstractmethod
    async def _do_login(self) -> None:
        """
        Website पर login करो।
        Email/password fill करके submit करो।
        """

    @abstractmethod
    async def _generate_and_download(self, prompt: str, prompt_idx: int) -> Optional[Path]:
        """
        एक prompt से video generate करो और download करो।
        Returns: Downloaded raw file path, या None अगर fail हो।
        """

    # ─── Utility Methods (सभी subclasses use कर सकते हैं) ──────────────────

    async def _safe_click(self, selector: str, timeout: int = 10_000) -> bool:
        """Safe click — element visible होने पर click करो।"""
        try:
            await self._page.wait_for_selector(selector, state="visible", timeout=timeout)
            await self._page.click(selector)
            return True
        except PlaywrightTimeout:
            logger.warning(f"Click timeout: {selector}")
            return False

    async def _safe_fill(self, selector: str, text: str, timeout: int = 10_000) -> bool:
        """Safe fill — element visible होने पर text fill करो।"""
        try:
            await self._page.wait_for_selector(selector, state="visible", timeout=timeout)
            await self._page.click(selector)
            await self._page.press(selector, "Control+A")
            await self._page.press(selector, "Delete")
            await asyncio.sleep(0.2)
            await self._page.type(selector, text, delay=0)
            return True
        except PlaywrightTimeout:
            logger.warning(f"Fill timeout: {selector}")
            return False

    async def _wait_for_download(self, trigger_action, timeout_sec: int = VIDEO_GEN_TIMEOUT_SEC) -> Optional[Path]:
        """
        Download trigger करो और file save करो।
        
        Usage:
            file = await self._wait_for_download(
                lambda: self._page.click("#download-btn")
            )
        """
        try:
            async with self._page.expect_download(timeout=timeout_sec * 1000) as dl_info:
                await trigger_action()
            download: Download = await dl_info.value
            dest = DOWNLOADS_DIR / download.suggested_filename
            await download.save_as(str(dest))
            logger.info(f"  📥 Download complete: {dest.name}")
            return dest
        except PlaywrightTimeout:
            logger.error(f"Download timeout after {timeout_sec}s")
            return None
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None

    async def _human_delay(self, min_sec: float = 1.0, max_sec: float = 3.0) -> None:
        """Human-like random delay।"""
        import random
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)

    async def _take_screenshot(self, name: str) -> None:
        """Debug screenshot लो।"""
        try:
            path = DOWNLOADS_DIR.parent / "logs" / f"{name}_{int(time.time())}.png"
            await self._page.screenshot(path=str(path), full_page=True)
            logger.debug(f"📸 Screenshot: {path.name}")
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# KLING AI AGENT
# Website: https://klingai.com
# ══════════════════════════════════════════════════════════════════════════════

class KlingAIAgent(BrowserAgent):
    """
    Kling AI (klingai.com) के लिए browser automation।
    
    ⚠️ IMPORTANT: इन selectors को अपने browser के Inspect Element से verify करें।
    Websites UI update करती रहती हैं — selectors बदल सकते हैं।
    """

    # ── Selectors (inspect element से verify करें) ─────────────────────────
    SEL_LOGIN_BTN      = 'a[href*="login"], button:has-text("Sign In"), button:has-text("Log In")'
    SEL_EMAIL_INPUT    = 'input[type="email"], input[name="email"]'
    SEL_PASSWORD_INPUT = 'input[type="password"]'
    SEL_SUBMIT_BTN     = 'button[type="submit"]'
    SEL_LOGGED_IN      = '[class*="user-avatar"], [class*="profile"], [data-testid="user-menu"]'

    SEL_TEXT_TO_VIDEO  = 'a[href*="text-to-video"], button:has-text("Text to Video")'
    SEL_PROMPT_INPUT   = 'textarea[placeholder*="prompt"], textarea[placeholder*="Describe"]'
    SEL_GENERATE_BTN   = 'button:has-text("Generate"), button:has-text("Create")'
    SEL_DOWNLOAD_BTN   = 'button:has-text("Download"), a[download]'
    SEL_VIDEO_READY    = '[class*="video-card"], [class*="result-video"], video'

    async def _is_logged_in(self) -> bool:
        try:
            await self._page.wait_for_selector(self.SEL_LOGGED_IN, timeout=5_000)
            return True
        except PlaywrightTimeout:
            return False

    async def _do_login(self) -> None:
        """Kling AI login flow।"""
        # Login page पर जाओ
        await self._safe_click(self.SEL_LOGIN_BTN, timeout=10_000)
        await self._human_delay(1, 2)

        # Credentials fill करो
        await self._safe_fill(self.SEL_EMAIL_INPUT, WEBSITE_EMAIL)
        await self._human_delay(0.5, 1)
        await self._safe_fill(self.SEL_PASSWORD_INPUT, WEBSITE_PASSWORD)
        await self._human_delay(0.5, 1)

        # Submit
        await self._safe_click(self.SEL_SUBMIT_BTN)

        # Login complete होने का wait
        try:
            await self._page.wait_for_selector(self.SEL_LOGGED_IN, timeout=30_000)
            logger.info("✅ Login successful")
        except PlaywrightTimeout:
            await self._take_screenshot("login_failed")
            raise RuntimeError("Login failed — check credentials or CAPTCHA")

    async def _generate_and_download(self, prompt: str, prompt_idx: int) -> Optional[Path]:
        """Kling AI पर video generate करो और download करो।"""

        # Text-to-Video section पर जाओ
        await self._safe_click(self.SEL_TEXT_TO_VIDEO)
        await self._page.wait_for_load_state("networkidle", timeout=15_000)
        await self._human_delay(1, 2)

        # Prompt fill करो
        filled = await self._safe_fill(self.SEL_PROMPT_INPUT, prompt, timeout=15_000)
        if not filled:
            await self._take_screenshot(f"prompt_fill_failed_{prompt_idx}")
            logger.error("Prompt input field nahi mila")
            return None

        await self._human_delay(1, 2)

        # Generate button click
        clicked = await self._safe_click(self.SEL_GENERATE_BTN)
        if not clicked:
            await self._take_screenshot(f"generate_btn_failed_{prompt_idx}")
            return None

        logger.info(f"  ⏳ Video generate ho rahi hai... (max {VIDEO_GEN_TIMEOUT_SEC}s wait)")

        # Video ready होने का wait (polling)
        video_ready = await self._wait_for_video_ready()
        if not video_ready:
            return None

        await self._human_delay(1, 2)

        # Download करो
        downloaded = await self._wait_for_download(
            lambda: self._page.click(self.SEL_DOWNLOAD_BTN),
            timeout_sec=60,
        )
        return downloaded

    async def _wait_for_video_ready(self) -> bool:
        """
        Video generation complete होने का wait (polling approach)।
        Progress bar/status text check करते रहो।
        """
        start = time.time()
        poll_interval = 10  # हर 10 seconds check करो

        while time.time() - start < VIDEO_GEN_TIMEOUT_SEC:
            try:
                # Video element visible है?
                await self._page.wait_for_selector(
                    self.SEL_VIDEO_READY,
                    state="visible",
                    timeout=poll_interval * 1000,
                )
                elapsed = int(time.time() - start)
                logger.info(f"  🎉 Video ready in {elapsed}s!")
                return True
            except PlaywrightTimeout:
                elapsed = int(time.time() - start)
                logger.info(f"  ⏳ Still generating... ({elapsed}s elapsed)")
                continue

        logger.error(f"Video generation timeout after {VIDEO_GEN_TIMEOUT_SEC}s")
        await self._take_screenshot("generation_timeout")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# RUNWAY ML AGENT
# Website: https://runwayml.com
# ══════════════════════════════════════════════════════════════════════════════

class RunwayAgent(BrowserAgent):
    """
    Runway ML के लिए browser automation।
    
    ⚠️ Selectors को अपने browser Inspect Element से verify करें।
    """

    SEL_LOGGED_IN   = '[data-testid="user-avatar"], [class*="UserAvatar"]'
    SEL_EMAIL_INPUT = 'input[name="email"]'
    SEL_PASS_INPUT  = 'input[name="password"]'
    SEL_SIGN_IN_BTN = 'button[type="submit"]:has-text("Sign In")'
    SEL_PROMPT_BOX  = 'textarea[placeholder*="Describe"]'
    SEL_GEN_BTN     = 'button:has-text("Generate")'
    SEL_DL_BTN      = 'button[aria-label*="Download"], button:has-text("Download")'
    SEL_VIDEO_DONE  = '[class*="generated-video"], [class*="OutputVideo"]'

    async def _is_logged_in(self) -> bool:
        try:
            await self._page.wait_for_selector(self.SEL_LOGGED_IN, timeout=5_000)
            return True
        except PlaywrightTimeout:
            return False

    async def _do_login(self) -> None:
        await self._page.goto("https://app.runwayml.com/login", wait_until="networkidle")
        await self._safe_fill(self.SEL_EMAIL_INPUT, WEBSITE_EMAIL)
        await self._human_delay(0.5, 1)
        await self._safe_fill(self.SEL_PASS_INPUT, WEBSITE_PASSWORD)
        await self._safe_click(self.SEL_SIGN_IN_BTN)
        try:
            await self._page.wait_for_selector(self.SEL_LOGGED_IN, timeout=30_000)
            logger.info("✅ Runway login successful")
        except PlaywrightTimeout:
            raise RuntimeError("Runway login failed")

    async def _generate_and_download(self, prompt: str, prompt_idx: int) -> Optional[Path]:
        await self._page.goto("https://app.runwayml.com", wait_until="networkidle")
        await self._human_delay(2, 3)

        await self._safe_fill(self.SEL_PROMPT_BOX, prompt)
        await self._human_delay(1, 2)
        await self._safe_click(self.SEL_GEN_BTN)

        logger.info(f"  ⏳ Runway video generating... (max {VIDEO_GEN_TIMEOUT_SEC}s)")

        # Wait for completion
        try:
            await self._page.wait_for_selector(
                self.SEL_VIDEO_DONE, timeout=VIDEO_GEN_TIMEOUT_SEC * 1000
            )
        except PlaywrightTimeout:
            logger.error("Runway generation timeout")
            return None

        return await self._wait_for_download(
            lambda: self._page.click(self.SEL_DL_BTN),
            timeout_sec=60,
        )


# ══════════════════════════════════════════════════════════════════════════════
# CUSTOM AGENT TEMPLATE
# अपनी website के लिए यह use करें
# ══════════════════════════════════════════════════════════════════════════════

class CustomVideoAgent(BrowserAgent):
    """
    Custom website के लिए template।
    
    Step 1: Website खोलो → F12 → Inspect Element
    Step 2: नीचे दिए selectors को अपनी website से match करो
    Step 3: _generate_and_download() में flow customize करो
    """

    # ── TODO: इन selectors को अपनी website से replace करें ─────────────────
    SEL_LOGGED_IN      = "#user-menu"           # Logged-in user element
    SEL_EMAIL_INPUT    = 'input[type="email"]'
    SEL_PASSWORD_INPUT = 'input[type="password"]'
    SEL_LOGIN_SUBMIT   = 'button[type="submit"]'
    SEL_PROMPT_INPUT   = 'textarea#prompt'       # Prompt text area
    SEL_GENERATE_BTN   = 'button#generate'       # Generate button
    SEL_VIDEO_READY    = 'video.result'          # Generated video element
    SEL_DOWNLOAD_BTN   = 'a#download-video'      # Download link/button

    async def _is_logged_in(self) -> bool:
        try:
            await self._page.wait_for_selector(self.SEL_LOGGED_IN, timeout=5_000)
            return True
        except PlaywrightTimeout:
            return False

    async def _do_login(self) -> None:
        """TODO: अपनी website का login flow यहाँ implement करें।"""
        await self._safe_fill(self.SEL_EMAIL_INPUT, WEBSITE_EMAIL)
        await self._safe_fill(self.SEL_PASSWORD_INPUT, WEBSITE_PASSWORD)
        await self._safe_click(self.SEL_LOGIN_SUBMIT)

        try:
            await self._page.wait_for_selector(self.SEL_LOGGED_IN, timeout=30_000)
            logger.info("✅ Login successful")
        except PlaywrightTimeout:
            await self._take_screenshot("login_failed")
            raise RuntimeError("Login failed — selectors check karein ya CAPTCHA handle karein")

    async def _generate_and_download(self, prompt: str, prompt_idx: int) -> Optional[Path]:
        """TODO: अपनी website का generation + download flow implement करें।"""

        # 1. Prompt fill करो
        await self._safe_fill(self.SEL_PROMPT_INPUT, prompt)
        await self._human_delay(1, 2)

        # 2. Generate click करो
        await self._safe_click(self.SEL_GENERATE_BTN)
        logger.info(f"  ⏳ Generating... (max {VIDEO_GEN_TIMEOUT_SEC}s)")

        # 3. Video ready होने का wait करो
        try:
            await self._page.wait_for_selector(
                self.SEL_VIDEO_READY,
                state="visible",
                timeout=VIDEO_GEN_TIMEOUT_SEC * 1000,
            )
        except PlaywrightTimeout:
            await self._take_screenshot(f"gen_timeout_{prompt_idx}")
            return None

        await self._human_delay(1, 2)

        # 4. Download करो
        return await self._wait_for_download(
            lambda: self._page.click(self.SEL_DOWNLOAD_BTN),
            timeout_sec=60,
        )


# ══════════════════════════════════════════════════════════════════════════════
# FACTORY — Website URL से सही Agent चुनो
# ══════════════════════════════════════════════════════════════════════════════

def create_agent() -> BrowserAgent:
    """
    WEBSITE_URL के आधार पर सही agent return करता है।
    अपनी website के agent को यहाँ add करें।
    """
    url = WEBSITE_URL.lower()

    if "klingai" in url or "kling" in url:
        logger.info("🤖 Agent: KlingAI")
        return KlingAIAgent()

    elif "runwayml" in url or "runway" in url:
        logger.info("🤖 Agent: Runway ML")
        return RunwayAgent()

    else:
        logger.info(f"🤖 Agent: Custom (URL: {WEBSITE_URL})")
        logger.warning("⚠️  CustomVideoAgent use ho raha hai — selectors customize karein!")
        return CustomVideoAgent()


# ── Sync wrapper (main.py में use के लिए) ─────────────────────────────────────

def run_browser_agent(row: VideoRow) -> list[Path]:
    """Async BrowserAgent को sync context mein chalata hai."""
    agent = create_agent()
    return asyncio.run(agent.process_video_row(row))
