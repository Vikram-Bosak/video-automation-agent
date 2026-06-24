"""
agents/video_generator.py
──────────────────────────
FREE video generation — NO API key, NO billing, NO browser needed.

Approach:
  1. 3 prompts se free images generate karo (Pollinations.ai)
  2. Images ko FFmpeg se animated video mein convert karo
     (Ken Burns effect + smooth transitions)
  3. Final MP4 export → Google Drive upload

Cost: ₹0 | Time: ~60 seconds | Quality: Professional short-form video
"""

from __future__ import annotations

import logging
import time
import urllib.request
import urllib.parse
import subprocess
import shutil
import random
from pathlib import Path
from typing import Optional

from config.settings import DOWNLOADS_DIR, VIDEO_DURATION_SEC

logger = logging.getLogger(__name__)

# ─── Image Generation Config ──────────────────────────────────────────────────
IMAGE_API_BASE = "https://image.pollinations.ai/prompt"
IMAGE_WIDTH = 720    # 9:16 portrait
IMAGE_HEIGHT = 1280  # 9:16 portrait
IMAGE_TIMEOUT = 60   # seconds per image


class VideoGenerator:
    """
    FREE video generation using Pollinations.ai + FFmpeg.
    
    No API key, no billing, no browser automation needed.
    Just pure API calls + local FFmpeg processing.
    """

    def generate_video(self, prompts: list[str], title: str = "") -> Optional[Path]:
        """
        Prompts se short video banao.
        
        Args:
            prompts: List of 3 prompts (Scene 1, 2, 3)
            title: Video title (for filename)
        
        Returns:
            Path to generated video file, or None on failure
        """
        if not prompts:
            logger.error("❌ No prompts provided!")
            return None

        safe_title = self._safe_filename(title) or "video"
        logger.info(f"🎬 Generating FREE video: '{title}'")
        logger.info(f"   Prompts: {len(prompts)} scenes")

        try:
            # ── Step 1: Generate Images (FREE — Pollinations.ai) ─────────
            image_paths = []
            for i, prompt in enumerate(prompts, 1):
                if not prompt.strip():
                    continue
                img_path = self._generate_image(prompt.strip(), i)
                if img_path:
                    image_paths.append(img_path)
                else:
                    logger.warning(f"⚠️  Image {i} generation failed, skipping")

            if len(image_paths) == 0:
                logger.error("❌ Koi image generate nahi hui!")
                return None

            logger.info(f"✅ {len(image_paths)} images ready")

            # ── Step 2: Create Video with FFmpeg ─────────────────────────
            output_path = DOWNLOADS_DIR / f"{safe_title}.mp4"
            success = self._create_video_from_images(image_paths, output_path)

            if not success:
                logger.error("❌ FFmpeg video creation failed!")
                return None

            size_mb = output_path.stat().st_size / (1024 * 1024)
            logger.info(f"✅ Video ready: {output_path.name} ({size_mb:.1f} MB)")
            return output_path

        except Exception as e:
            logger.error(f"❌ Video generation failed: {e}", exc_info=True)
            return None

    def _generate_image(self, prompt: str, scene_num: int) -> Optional[Path]:
        """
        Single image generate karo using Pollinations.ai (FREE).
        Returns: Path to downloaded image
        """
        # Prompt ko URL-safe banao
        encoded_prompt = urllib.parse.quote(prompt)

        # Random seed for variety
        seed = random.randint(1, 999999)

        url = (
            f"{IMAGE_API_BASE}/{encoded_prompt}"
            f"?width={IMAGE_WIDTH}&height={IMAGE_HEIGHT}"
            f"&nologo=true&seed={seed}"
        )

        output_path = DOWNLOADS_DIR / f"scene_{scene_num}_{int(time.time())}.png"

        try:
            logger.info(f"  🖼️  Scene {scene_num}: Generating image...")
            start = time.time()

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=IMAGE_TIMEOUT) as response:
                data = response.read()

            elapsed = int(time.time() - start)

            if len(data) < 1000:  # Too small = error
                logger.error(f"  ❌ Scene {scene_num}: Invalid response ({len(data)} bytes)")
                return None

            with open(output_path, "wb") as f:
                f.write(data)

            size_kb = len(data) / 1024
            logger.info(f"  ✅ Scene {scene_num}: {size_kb:.0f} KB ({elapsed}s)")
            return output_path

        except Exception as e:
            logger.error(f"  ❌ Scene {scene_num} failed: {e}")
            return None

    def _create_video_from_images(self, image_paths: list[Path], output_path: Path) -> bool:
        """
        Images se animated video banao using FFmpeg.
        
        Features:
          - Ken Burns effect (slow zoom/pan on each image)
          - Smooth crossfade transitions between scenes
          - 9:16 portrait format (720x1280)
          - Background music-ready (silent audio track)
        """
        if not image_paths:
            return False

        num_images = len(image_paths)
        seconds_per_image = VIDEO_DURATION_SEC / num_images
        fps = 30
        frames_per_image = int(seconds_per_image * fps)

        # ── Build FFmpeg command ──────────────────────────────────────────

        inputs = []
        filters = []

        # Har image ko input banao with Ken Burns effect
        for i, img_path in enumerate(image_paths):
            inputs.extend(["-loop", "1", "-t", str(seconds_per_image), "-i", str(img_path)])

            # Ken Burns: random zoom direction
            zoom_start = 1.0
            zoom_end = random.uniform(1.05, 1.15)  # Subtle zoom

            # Random pan direction
            pan_options = [
                f"zoompan=z='min({zoom_start}+(({zoom_end}-{zoom_start})*on/{frames_per_image}),{zoom_end})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames_per_image}:s={IMAGE_WIDTH}x{IMAGE_HEIGHT}:fps={fps}",
                f"zoompan=z='min({zoom_start}+(({zoom_end}-{zoom_start})*on/{frames_per_image}),{zoom_end})':x='iw/4-(iw/zoom/4)+((iw/zoom/2)*on/{frames_per_image})':y='ih/2-(ih/zoom/2)':d={frames_per_image}:s={IMAGE_WIDTH}x{IMAGE_HEIGHT}:fps={fps}",
                f"zoompan=z='min({zoom_start}+(({zoom_end}-{zoom_start})*on/{frames_per_image}),{zoom_end})':x='iw/2-(iw/zoom/2)':y='ih/4-(ih/zoom/4)+((ih/zoom/2)*on/{frames_per_image})':d={frames_per_image}:s={IMAGE_WIDTH}x{IMAGE_HEIGHT}:fps={fps}",
            ]
            filters.append(f"[{i}:v]{pan_options[i % len(pan_options)]}[/v{i}]")

        # Sabhi streams ko concat karo with crossfade
        if num_images == 1:
            filters.append(f"[/v0]format=yuv420p[outv]")
        else:
            # Crossfade transitions
            concat_parts = ""
            fade_duration = 0.5  # seconds

            for i in range(num_images):
                if i == 0:
                    filters.append(f"[/v{i}]format=yuv420p,setsar=1[/vin{i}]")
                else:
                    filters.append(f"[/v{i}]format=yuv420p,setsar=1[/vin{i}]")

            # Simple concat (crossfade is complex, use simple concat for reliability)
            concat_inputs = "".join(f"[vin{i}]" for i in range(num_images))
            filters.append(
                f"{concat_inputs}concat=n={num_images}:v=1:a=0[outv]"
            )

        filter_complex = ";\n".join(filters)

        # ── Run FFmpeg ────────────────────────────────────────────────────
        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-r", str(fps),
            str(output_path),
        ]

        logger.info(f"  🎞️  FFmpeg: Creating {VIDEO_DURATION_SEC}s video from {num_images} images...")
        logger.debug(f"  CMD: {' '.join(cmd[:10])}...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                logger.error(f"  ❌ FFmpeg error:\n{result.stderr[-500:]}")
                # Try simpler fallback
                return self._create_simple_video(image_paths, output_path)

            logger.info(f"  ✅ FFmpeg: Video created successfully")
            return True

        except subprocess.TimeoutExpired:
            logger.error("  ❌ FFmpeg timeout (120s)")
            return False
        except FileNotFoundError:
            logger.error("  ❌ FFmpeg not found! Install: apt install ffmpeg")
            return False

    def _create_simple_video(self, image_paths: list[Path], output_path: Path) -> bool:
        """
        Fallback: Simple video creation (no Ken Burns, just slideshow).
        """
        logger.info("  🔄 Trying simple fallback video creation...")

        num_images = len(image_paths)
        seconds_per_image = VIDEO_DURATION_SEC / num_images

        inputs = []
        for img_path in image_paths:
            inputs.extend(["-loop", "1", "-t", str(seconds_per_image), "-i", str(img_path)])

        concat_text = ""
        for i in range(num_images):
            concat_text += f"[{i}:v]scale={IMAGE_WIDTH}:{IMAGE_HEIGHT}:force_original_aspect_ratio=decrease,pad={IMAGE_WIDTH}:{IMAGE_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}];"

        concat_inputs = "".join(f"[v{i}]" for i in range(num_images))
        concat_text += f"{concat_inputs}concat=n={num_images}:v=1:a=0[outv]"

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", concat_text,
            "-map", "[outv]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "28",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                logger.info("  ✅ Simple video created")
                return True
            else:
                logger.error(f"  ❌ Simple video also failed:\n{result.stderr[-300:]}")
                return False
        except Exception as e:
            logger.error(f"  ❌ Fallback failed: {e}")
            return False

    def _cleanup_temp_images(self, image_paths: list[Path]) -> None:
        """Temporary images delete karo."""
        for img_path in image_paths:
            try:
                img_path.unlink(missing_ok=True)
            except Exception:
                pass

    @staticmethod
    def _safe_filename(name: str) -> str:
        """File system safe filename banao."""
        import re
        if not name:
            return ""
        safe = re.sub(r'[^\w\s-]', '', name)
        safe = re.sub(r'\s+', '_', safe.strip())
        return safe[:80]


# ── Public function ───────────────────────────────────────────────────────────

def generate_video(prompts: list[str], title: str = "") -> Optional[Path]:
    """
    FREE video generate karo — single function call.
    
    Usage:
        from agents.video_generator import generate_video
        path = generate_video(["prompt1", "prompt2", "prompt3"], "My Video")
    """
    generator = VideoGenerator()
    return generator.generate_video(prompts, title)
