"""
agents/video_generator.py
──────────────────────────
LTX-2.3 (Lightricks) — Open Source Text-to-Video
Runs locally on 8GB VRAM GPU.

Model: Lightricks/LTX-2.3 (distilled + fp8)
Pipeline: Diffusers + custom LTX pipelines

Prerequisites:
  1. NVIDIA GPU with 8GB+ VRAM
  2. CUDA installed
  3. pip install -r requirements-gpu.txt
  4. python -m scripts.setup_ltx (download models)
"""

from __future__ import annotations

import logging
import os
import time
import subprocess
from pathlib import Path
from typing import Optional

from config.settings import (
    DOWNLOADS_DIR,
    VIDEO_DURATION_SEC,
    LTX_MODEL_PATH,
    LTX_DEVICE,
    LTX_QUANTIZATION,
)

logger = logging.getLogger(__name__)


class VideoGenerator:
    """
    LTX-2.3 se video generate karta hai.
    8GB VRAM pe distilled + fp8 model chalta hai.
    """

    def __init__(self):
        self._pipeline = None
        self._device = LTX_DEVICE

    def generate_video(self, prompts: list[str], title: str = "") -> Optional[Path]:
        """
        3 prompts se 24s video banao.
        Har prompt = 8s clip → join karo.
        """
        if not prompts:
            logger.error("❌ No prompts!")
            return None

        safe = self._safe_name(title) or "video"
        logger.info(f"🎬 LTX-2.3: '{title}' | {len(prompts)} clips")

        try:
            self._load_model()

            clips = []
            for i, p in enumerate(prompts[:3], 1):
                if not p.strip():
                    continue
                logger.info(f"\n🎥 Clip {i}/3: {p[:80]}...")
                clip = self._gen_clip(p.strip(), i)
                if clip:
                    clips.append(clip)
                    logger.info(f"   ✅ Clip {i}: {clip.name}")
                else:
                    logger.warning(f"   ⚠️ Clip {i} failed")

            if not clips:
                logger.error("❌ No clips generated!")
                return None

            # Join clips
            out = DOWNLOADS_DIR / f"{safe}.mp4"
            if len(clips) == 1:
                import shutil
                shutil.copy2(clips[0], out)
            else:
                self._join_clips(clips, out)

            # Cleanup temp clips
            for c in clips:
                try:
                    c.unlink(missing_ok=True)
                except Exception:
                    pass

            mb = out.stat().st_size / (1024 * 1024)
            logger.info(f"\n✅ Video: {out.name} ({mb:.1f} MB)")
            return out

        except Exception as e:
            logger.error(f"❌ {e}", exc_info=True)
            return None

    def _load_model(self):
        """LTX-2.3 pipeline load karo (lazy loading)."""
        if self._pipeline is not None:
            return

        logger.info("📥 Loading LTX-2.3 model...")
        t0 = time.time()

        try:
            import torch
            from diffusers import LTXPipeline
            from diffusers.utils import export_to_video

            model_path = LTX_MODEL_PATH or "Lightricks/LTX-2.3-distilled"

            # fp8 quantization for 8GB VRAM
            if LTX_QUANTIZATION == "fp8":
                logger.info("   Using FP8 quantization (8GB VRAM mode)")
                self._pipeline = LTXPipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch.float16,
                    variant="fp8" if "fp8" in model_path else None,
                )
            else:
                self._pipeline = LTXPipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch.float16,
                )

            self._pipeline.to(self._device)

            # Memory optimization for 8GB VRAM
            if self._device == "cuda":
                self._pipeline.enable_model_cpu_offload()
                try:
                    self._pipeline.enable_xformers_memory_efficient_attention()
                    logger.info("   xFormers attention enabled")
                except Exception:
                    pass

            elapsed = int(time.time() - t0)
            logger.info(f"✅ Model loaded ({elapsed}s) | Device: {self._device}")

        except ImportError as e:
            raise RuntimeError(
                f"❌ GPU dependencies not installed!\n"
                f"   Run: pip install -r requirements-gpu.txt\n"
                f"   Error: {e}"
            )
        except Exception as e:
            raise RuntimeError(f"❌ Model load failed: {e}")

    def _gen_clip(self, prompt: str, num: int) -> Optional[Path]:
        """Ek 8-second clip generate karo."""
        import torch
        from diffusers.utils import export_to_video

        try:
            t0 = time.time()

            # LTX-2.3 video generation
            # 8 seconds × 24fps = 192 frames
            # But distilled model: 8 steps is enough
            output = self._pipeline(
                prompt=prompt,
                num_frames=192,         # 8s × 24fps
                num_inference_steps=8,   # Distilled: 8 steps
                guidance_scale=1.0,      # CFG=1 for distilled
                height=768,              # 9:16 portrait
                width=432,
                generator=torch.Generator(self._device).manual_seed(42 + num),
            )

            # Save clip
            clip_path = DOWNLOADS_DIR / f"clip_{num}_{int(time.time())}.mp4"
            export_to_video(output.frames[0], str(clip_path), fps=24)

            elapsed = int(time.time() - t0)
            kb = clip_path.stat().st_size / 1024
            logger.info(f"   ⏱️ {elapsed}s | {kb:.0f} KB")

            # Free VRAM
            if self._device == "cuda":
                torch.cuda.empty_cache()

            return clip_path

        except torch.cuda.OutOfMemoryError:
            logger.error(f"   ❌ OOM! Try smaller resolution or fewer frames")
            if self._device == "cuda":
                torch.cuda.empty_cache()
            return None
        except Exception as e:
            logger.error(f"   ❌ Clip {num}: {e}")
            return None

    def _join_clips(self, clips: list[Path], out: Path):
        """FFmpeg se clips join karo."""
        concat_file = DOWNLOADS_DIR / "concat.txt"
        with open(concat_file, "w") as f:
            for c in clips:
                f.write(f"file '{c.absolute()}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(out),
        ]

        logger.info(f"  🎞️ Joining {len(clips)} clips...")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            logger.error(f"  ❌ FFmpeg: {r.stderr[-200:]}")
        else:
            logger.info(f"  ✅ Joined!")

    @staticmethod
    def _safe_name(s: str) -> str:
        import re
        if not s:
            return ""
        return re.sub(r'\s+', '_', re.sub(r'[^\w\s-]', '', s).strip())[:80]


def generate_video(prompts: list[str], title: str = "") -> Optional[Path]:
    return VideoGenerator().generate_video(prompts, title)
