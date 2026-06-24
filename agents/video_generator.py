"""
agents/video_generator.py
──────────────────────────
FREE video generation — NO API key, NO billing, NO browser needed.

Approach:
  1. 3 prompts se free images generate karo (Pollinations.ai)
  2. Images ko FFmpeg se short video mein convert karo
  3. Final MP4 export → Google Drive upload

Cost: ₹0 | Time: ~45 seconds | Quality: Professional short-form video
"""

from __future__ import annotations

import logging
import time
import urllib.request
import urllib.parse
import subprocess
import random
from pathlib import Path
from typing import Optional

from config.settings import DOWNLOADS_DIR, VIDEO_DURATION_SEC

logger = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────
IMAGE_API = "https://image.pollinations.ai/prompt"
IMG_W, IMG_H = 720, 1280  # 9:16 portrait
IMG_TIMEOUT = 60


class VideoGenerator:
    """
    FREE video generation: Pollinations.ai (images) + FFmpeg (video).
    No API key, no billing, no browser automation.
    """

    def generate_video(self, prompts: list[str], title: str = "") -> Optional[Path]:
        """3 prompts → images → animated MP4 video."""
        if not prompts:
            logger.error("❌ No prompts!")
            return None

        safe_title = self._safe_filename(title) or "video"
        logger.info(f"🎬 Generating: '{title}' | {len(prompts)} scenes")

        try:
            # ── Step 1: Generate images (FREE) ───────────────────────────
            images = []
            for i, prompt in enumerate(prompts, 1):
                if not prompt.strip():
                    continue
                img = self._gen_image(prompt.strip(), i)
                if img:
                    images.append(img)

            if not images:
                logger.error("❌ No images generated!")
                return None

            logger.info(f"✅ {len(images)} images ready")

            # ── Step 2: Create video with FFmpeg ─────────────────────────
            out = DOWNLOADS_DIR / f"{safe_title}.mp4"

            if not self._make_video(images, out):
                return None

            mb = out.stat().st_size / (1024 * 1024)
            logger.info(f"✅ Video: {out.name} ({mb:.1f} MB)")
            return out

        except Exception as e:
            logger.error(f"❌ Failed: {e}", exc_info=True)
            return None

    def _gen_image(self, prompt: str, n: int) -> Optional[Path]:
        """Pollinations.ai se FREE image download karo."""
        enc = urllib.parse.quote(prompt)
        seed = random.randint(1, 999999)
        url = f"{IMAGE_API}/{enc}?width={IMG_W}&height={IMG_H}&nologo=true&seed={seed}"

        out = DOWNLOADS_DIR / f"scene_{n}_{int(time.time())}.png"
        try:
            t0 = time.time()
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=IMG_TIMEOUT) as r:
                data = r.read()

            if len(data) < 1000:
                logger.error(f"  ❌ Scene {n}: Bad response ({len(data)}B)")
                return None

            out.write_bytes(data)
            kb = len(data) / 1024
            logger.info(f"  ✅ Scene {n}: {kb:.0f} KB ({int(time.time()-t0)}s)")
            return out

        except Exception as e:
            logger.error(f"  ❌ Scene {n}: {e}")
            return None

    def _make_video(self, images: list[Path], out: Path) -> bool:
        """
        FFmpeg se images se video banao.
        Simple scale → pad → concat — fast and reliable.
        """
        n = len(images)
        dur = VIDEO_DURATION_SEC / n
        fps = 24

        inputs = []
        filters = []

        for i, img in enumerate(images):
            inputs += ["-loop", "1", "-t", str(dur), "-i", str(img)]
            # Scale to exact size, pad if needed, set fps
            filters.append(
                f"[{i}:v]scale={IMG_W}:{IMG_H}:force_original_aspect_ratio=decrease,"
                f"pad={IMG_W}:{IMG_H}:(ow-iw)/2:(oh-ih)/2:black,"
                f"setsar=1,fps={fps},format=yuv420p[v{i}]"
            )

        concat_in = "".join(f"[v{i}]" for i in range(n))
        filters.append(f"{concat_in}concat=n={n}:v=1:a=0[outv]")

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", ";".join(filters),
            "-map", "[outv]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "26",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(out),
        ]

        logger.info(f"  🎞️  FFmpeg: {VIDEO_DURATION_SEC}s video from {n} scenes...")

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                logger.error(f"  ❌ FFmpeg: {r.stderr[-300:]}")
                return False
            logger.info(f"  ✅ Video created!")
            return True
        except subprocess.TimeoutExpired:
            logger.error("  ❌ FFmpeg timeout")
            return False
        except FileNotFoundError:
            logger.error("  ❌ FFmpeg not found!")
            return False

    @staticmethod
    def _safe_filename(name: str) -> str:
        import re
        if not name:
            return ""
        return re.sub(r'\s+', '_', re.sub(r'[^\w\s-]', '', name).strip())[:80]


def generate_video(prompts: list[str], title: str = "") -> Optional[Path]:
    """FREE video — single function call."""
    return VideoGenerator().generate_video(prompts, title)
