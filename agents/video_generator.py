"""
agents/video_generator.py
──────────────────────────
Google Vids (Veo 3.1) automation via Playwright.

Based on actual UI screenshot analysis:
- Right sidebar: AI Video Clip panel
- Textarea: "Describe your video..."
- Model: Veo 3.1
- Format: Portrait (9:16)
- Timeline at bottom: clips + duration
- Download: File → Download → MP4

Flow:
  1. Google Vids khole
  2. Naya project banao
  3. Har prompt se 8s clip generate karo
  4. Sab clips timeline mein add ho jayenge
  5. Final 24s video download karo
"""

from __future__ import annotations

import asyncio
import logging
import time
import shutil
import os
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
    DOWNLOADS_DIR,
    BROWSER_HEADLESS,
    BROWSER_SLOW_MO,
    VIDEO_GEN_TIMEOUT_SEC,
)

logger = logging.getLogger(__name__)

COOKIES_FILE = Path("cookies.json")
GOOGLE_VIDS_URL = "https://docs.google.com/videos"


class VideoGenerator:
    """
    Google Vids automation — Veo 3.1 se FREE video generation.
    """

    def __init__(self):
        self._pw = None
        self._browser: Optional[Browser] = None
        self._ctx: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    def generate_video(self, prompts: list[str], title: str = "") -> Optional[Path]:
        return asyncio.run(self._run(prompts, title))

    async def _run(self, prompts: list[str], title: str = "") -> Optional[Path]:
        if not prompts:
            logger.error("❌ No prompts!")
            return None

        safe = self._safe_name(title) or "video"
        logger.info(f"🎬 Google Vids: '{title}' | {len(prompts)} clips")

        try:
            await self._start_browser()
            await self._login()
            await self._new_project()
            await self._delay(3, 5)

            for i, p in enumerate(prompts, 1):
                if not p.strip():
                    continue
                logger.info(f"\n🎥 Clip {i}/{len(prompts)}: {p[:80]}...")
                ok = await self._gen_clip(p.strip(), i)
                if not ok:
                    logger.warning(f"   ⚠️  Clip {i} failed")
                await self._delay(2, 4)

            out = DOWNLOADS_DIR / f"{safe}.mp4"
            result = await self._download(out)

            if result:
                mb = result.stat().st_size / (1024 * 1024)
                logger.info(f"\n✅ Video: {result.name} ({mb:.1f} MB)")
            return result

        except Exception as e:
            logger.error(f"❌ {e}", exc_info=True)
            return None
        finally:
            await self._stop()

    # ─── Browser ──────────────────────────────────────────────────────────

    async def _start_browser(self):
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=BROWSER_HEADLESS,
            slow_mo=BROWSER_SLOW_MO,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                   "--disable-blink-features=AutomationControlled"],
        )
        opts = {
            "viewport": {"width": 1366, "height": 768},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
            "accept_downloads": True,
        }
        if COOKIES_FILE.exists():
            opts["storage_state"] = str(COOKIES_FILE)
            logger.info("🍪 Cookies loaded")
        self._ctx = await self._browser.new_context(**opts)
        self._page = await self._ctx.new_page()
        logger.info(f"✅ Browser ready | Headless: {BROWSER_HEADLESS}")

    async def _stop(self):
        try:
            if self._ctx:
                await self._ctx.storage_state(path=str(COOKIES_FILE))
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass

    # ─── Login ─────────────────────────────────────────────────────────────

    async def _login(self):
        # ── Step 1: Validate cookies first ──────────────────────────────
        if COOKIES_FILE.exists():
            try:
                import json as _json
                cookie_data = _json.loads(COOKIES_FILE.read_text())
                cookies = cookie_data.get("cookies", [])
                if not cookies:
                    logger.error("❌ cookies.json is EMPTY — no cookies found!")
                    logger.error("   → Solution: Refresh cookies (see README)")
                    raise RuntimeError("cookies.json is empty. Google session expired. Please refresh cookies.")
                
                # Check if cookies have Google auth tokens
                google_cookies = [c for c in cookies if "google" in c.get("domain", "")]
                if not google_cookies:
                    logger.error("❌ cookies.json has no Google cookies!")
                    raise RuntimeError("No Google cookies found. Please refresh cookies.")
                
                logger.info(f"🍪 Cookies loaded: {len(cookies)} total, {len(google_cookies)} Google cookies")
            except RuntimeError:
                raise
            except Exception as e:
                logger.warning(f"⚠️  cookies.json validation failed: {e}")

        await self._page.goto(GOOGLE_VIDS_URL, wait_until="domcontentloaded", timeout=60_000)
        await self._delay(5, 8)
        url = self._page.url
        logger.info(f"📍 {url}")

        if "accounts.google.com" in url or "signin" in url.lower():
            logger.error("❌ Google login page detected — cookies are EXPIRED!")
            logger.error("   ┌─────────────────────────────────────────────────┐")
            logger.error("   │  HOW TO REFRESH COOKIES:                        │")
            logger.error("   │  1. Open Chrome → login to accounts.google.com  │")
            logger.error("   │  2. Go to docs.google.com/videos                │")
            logger.error("   │  3. Install 'EditThisCookie' extension           │")
            logger.error("   │  4. Export cookies → base64 encode               │")
            logger.error("   │  5. Update GOOGLE_COOKIES in GitHub Secrets      │")
            logger.error("   └─────────────────────────────────────────────────┘")
            email = os.environ.get("GOOGLE_ACCOUNT_EMAIL", "")
            pw = os.environ.get("GOOGLE_ACCOUNT_PASSWORD", "")
            if email and pw:
                logger.info(f"🔐 Login: {email[:5]}***")
                await self._page.goto("https://accounts.google.com/signin", wait_until="networkidle")
                await self._fill('input[type="email"]', email)
                await self._click('#identifierNext button, button:has-text("Next")')
                await self._delay(2, 3)
                await self._fill('input[type="password"]', pw)
                await self._click('#passwordNext button, button:has-text("Next")')
                await self._delay(3, 5)
                logger.info("✅ Logged in")
            else:
                raise RuntimeError(
                    "Google login required but no credentials found!\n"
                    "Set GOOGLE_ACCOUNT_EMAIL + GOOGLE_ACCOUNT_PASSWORD in GitHub Secrets,\n"
                    "OR refresh cookies.json via browser export."
                )
        else:
            logger.info("✅ Already logged in")

    # ─── Project ───────────────────────────────────────────────────────────

    async def _new_project(self):
        logger.info("📹 Creating project...")
        await self._page.goto(GOOGLE_VIDS_URL, wait_until="domcontentloaded", timeout=60_000)
        await self._delay(5, 8)  # Wait for dynamic content to load
        await self._delay(2, 3)

        # Click "Blank video" template — verified selectors for Google Vids UI
        for sel in [
            '[role="option"]:has-text("Blank video")',           # Actual: listbox option
            '.docs-homescreen-templates-templateview:has-text("Blank video")',  # Actual class
            'text=Blank video',                                  # Simple text match
            '[role="listbox"] [role="option"]',                  # Any template option
            '.docs-homescreen-templates-templateview',           # First template
            'button:has-text("Blank video")',                    # Fallback
            'button:has-text("New video")',                      # Fallback
            'button:has-text("Create")',                         # Fallback
        ]:
            if await self._click(sel, timeout=5000):
                logger.info(f"✅ Clicked: {sel}")
                break
        else:
            # Last resort: try clicking by coordinates (template card area)
            logger.warning("Standard selectors failed, trying coordinate click...")
            try:
                # Click in the template area (top-left of content)
                await self._page.mouse.click(300, 170)
                await self._delay(2, 3)
            except Exception as e:
                raise RuntimeError(f"Create button nahi mila! Error: {e}")

        await self._page.wait_for_url("**/videos/d/**", timeout=30_000)
        await self._delay(3, 5)
        logger.info("✅ Project created")

    # ─── Clip Generation ───────────────────────────────────────────────────

    async def _gen_clip(self, prompt: str, num: int) -> bool:
        # AI panel open karo (right sidebar Veo icon)
        if not await self._open_panel():
            return False
        await self._delay(1, 2)

        # Prompt type karo — textarea "Describe your video..."
        filled = await self._fill(
            'textarea[placeholder*="Describe"], textarea[placeholder*="8-second"], '
            '[data-placeholder*="Describe"], textarea',
            prompt, timeout=10_000
        )
        if not filled:
            await self._shot(f"prompt_fail_{num}")
            return False
        await self._shot(f"prompt_{num}")

        # Generate button click
        clicked = await self._click(
            'button:has-text("Generate"), button.videoGenCreationViewGenerateButton',
            timeout=10_000
        )
        if not clicked:
            await self._shot(f"gen_fail_{num}")
            return False

        logger.info(f"   ⏳ Generating... (max {VIDEO_GEN_TIMEOUT_SEC}s)")

        # Wait for clip ready
        ready = await self._wait_ready(num)
        if not ready:
            return False

        # Add to timeline
        await self._delay(1, 2)
        for sel in [
            'button:has-text("Add to video")',
            'button:has-text("Insert")',
            'button:has-text("Add")',
            '[aria-label*="Add to timeline"]',
        ]:
            if await self._click(sel, timeout=5_000):
                logger.info(f"   ✅ Clip {num} added")
                break

        await self._delay(2, 3)
        return True

    async def _open_panel(self) -> bool:
        # Check if already open
        try:
            if await self._page.is_visible('textarea[placeholder*="Describe"]', timeout=2000):
                return True
        except Exception:
            pass

        # Click Veo/AI icon in sidebar
        for sel in [
            '[aria-label="Generate an AI video clip"]',
            '[aria-label*="AI video clip"]',
            'button:has-text("AI video clip")',
            '[data-panel-id="veo"]',
            'button[title*="Veo"]',
        ]:
            if await self._click(sel, timeout=3000):
                await self._delay(1, 2)
                return True

        await self._shot("panel_fail")
        return False

    async def _wait_ready(self, num: int) -> bool:
        start = time.time()
        while time.time() - start < VIDEO_GEN_TIMEOUT_SEC:
            elapsed = int(time.time() - start)
            for sel in [
                'button:has-text("Add to video")',
                'button:has-text("Insert")',
                '.generated-clip',
            ]:
                try:
                    if await self._page.is_visible(sel, timeout=3000):
                        logger.info(f"   🎉 Clip {num} ready! ({elapsed}s)")
                        await self._shot(f"ready_{num}")
                        return True
                except Exception:
                    pass
            if elapsed % 15 == 0:
                logger.info(f"   ⏳ {elapsed}s...")
            await asyncio.sleep(5)

        logger.error(f"Clip {num} timeout!")
        return False

    # ─── Download ──────────────────────────────────────────────────────────

    async def _download(self, out: Path) -> Optional[Path]:
        logger.info("📥 Downloading...")
        for seq in [
            [('button:has-text("Download")', 5000)],
            [('button[aria-label="File"], button:has-text("File")', 5000),
             ('li:has-text("Download"), button:has-text("Download")', 5000)],
        ]:
            try:
                async with self._page.expect_download(timeout=300_000) as dl:
                    for sel, t in seq[:-1]:
                        await self._click(sel, t)
                        await self._delay(0.5, 1)
                    await self._click(seq[-1][0], seq[-1][1])
                d: Download = await dl.value
                dest = out.parent / d.suggested_filename
                await d.save_as(str(dest))
                if dest != out:
                    shutil.move(str(dest), str(out))
                logger.info(f"✅ Downloaded: {out.name}")
                return out
            except Exception:
                continue
        return None

    # ─── Helpers ───────────────────────────────────────────────────────────

    async def _click(self, sel: str, timeout: int = 10000) -> bool:
        try:
            await self._page.wait_for_selector(sel, state="visible", timeout=timeout)
            await self._page.click(sel)
            return True
        except Exception:
            return False

    async def _fill(self, sel: str, text: str, timeout: int = 10000) -> bool:
        try:
            await self._page.wait_for_selector(sel, state="visible", timeout=timeout)
            await self._page.click(sel)
            await self._page.press(sel, "Control+A")
            await self._page.press(sel, "Delete")
            await asyncio.sleep(0.2)
            await self._page.type(sel, text, delay=0)
            return True
        except Exception:
            return False

    async def _delay(self, mn: float = 1, mx: float = 3):
        import random
        await asyncio.sleep(random.uniform(mn, mx))

    async def _shot(self, name: str):
        try:
            p = DOWNLOADS_DIR.parent / "logs" / f"{name}_{int(time.time())}.png"
            await self._page.screenshot(path=str(p), full_page=False)
        except Exception:
            pass

    @staticmethod
    def _safe_name(s: str) -> str:
        import re
        if not s:
            return ""
        return re.sub(r'\s+', '_', re.sub(r'[^\w\s-]', '', s).strip())[:80]


def generate_video(prompts: list[str], title: str = "") -> Optional[Path]:
    return VideoGenerator().generate_video(prompts, title)
