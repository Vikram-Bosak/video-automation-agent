"""
agents/voice_generator.py
─────────────────────────
Prompts se dialogue extract karke TTS voice generate karta hai.
FREE — uses Microsoft Edge TTS (edge-tts).

Flow:
  1. Prompt se dialogue/narration extract karo
  2. edge-tts se audio banao
  3. Har scene ka audio file return karo
"""

from __future__ import annotations

import logging
import re
import asyncio
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Voice selection — kid-friendly, clear, warm
VOICE_MALE = "en-US-GuyNeural"      # KIDO (gorilla) — strong, warm
VOICE_FEMALE = "en-US-JennyNeural"  # BUM (cat) — soft, clear
VOICE_NARRATOR = "en-US-AriaNeural" # Narrator — friendly, educational

# Fallback voice
VOICE_DEFAULT = "en-US-AriaNeural"


def extract_dialogues(prompt: str) -> list[dict]:
    """
    Prompt se dialogue lines extract karo.
    Returns: [{"speaker": "KIDO", "text": "...", "voice": "..."}]
    """
    dialogues = []
    
    # Pattern: "KIDO says: ..." or "BUM: ..." or "He says: ..."
    # Also match quoted dialogue: "Can YOU say RED?"
    
    # Split by common separators
    parts = re.split(r'[|]', prompt)
    
    for part in parts:
        part = part.strip()
        
        # Match dialogue patterns
        # "KIDO says slowly: "R... E... D... RED!""
        # "She says slowly: "This is… RED.""
        # "He holds it toward camera... saying: "RED!""
        patterns = [
            r'(?:KIDO|He|She)\s+(?:says?|says?\s+slowly|whispers?|shouts?|calls?\s+out):\s*["\u201c](.+?)["\u201d]',
            r'(?:BUM|She|He)\s+(?:says?|says?\s+slowly):\s*["\u201c](.+?)["\u201d]',
            r'["\u201c](Can\s+YOU\s+say\s+\w+[\?\.]?)["\u201d]',
            r'["\u201c](\w+[\.\!\?])["\u201d]',
            r'KIDO\s+says?\s+slowly:\s*["\u201c](.+?)["\u201d]',
            r'BUM\s*:\s*["\u201c](.+?)["\u201d]',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, part, re.IGNORECASE)
            for match in matches:
                # Determine speaker
                speaker = "NARRATOR"
                voice = VOICE_NARRATOR
                
                if "KIDO" in part[:part.find(match) if match in part else 0]:
                    speaker = "KIDO"
                    voice = VOICE_MALE
                elif "BUM" in part[:part.find(match) if match in part else 0]:
                    speaker = "BUM"
                    voice = VOICE_FEMALE
                elif "Can YOU say" in match:
                    speaker = "BUM"
                    voice = VOICE_FEMALE
                
                dialogues.append({
                    "speaker": speaker,
                    "text": match.strip(),
                    "voice": voice,
                })
    
    # If no dialogues found, create a simple narration from the prompt
    if not dialogues:
        # Extract the most important sentence
        clean = re.sub(r'CHARACTER.*?LOCK.*', '', prompt, flags=re.DOTALL)
        clean = re.sub(r'Art style:.*', '', clean)
        clean = re.sub(r'Camera:.*', '', clean)
        clean = re.sub(r'Sound:.*', '', clean)
        clean = clean.strip()[:200]
        
        if clean:
            dialogues.append({
                "speaker": "NARRATOR",
                "text": clean,
                "voice": VOICE_NARRATOR,
            })
    
    return dialogues


async def _generate_tts(text: str, voice: str, output_path: Path) -> bool:
    """Edge TTS se audio generate karo."""
    try:
        import edge_tts
        
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))
        return output_path.exists() and output_path.stat().st_size > 100
    except Exception as e:
        logger.error(f"  ❌ TTS failed: {e}")
        return False


def generate_voice(prompt: str, scene_num: int, output_dir: Path) -> Optional[Path]:
    """
    Ek scene ka voice generate karo.
    Returns: Path to audio file (WAV/MP3)
    """
    dialogues = extract_dialogues(prompt)
    
    if not dialogues:
        logger.warning(f"  ⚠️  Scene {scene_num}: No dialogues found in prompt")
        return None
    
    # Use first dialogue for this scene
    d = dialogues[0]
    text = d["text"]
    voice = d["voice"]
    
    logger.info(f"  🎤 Scene {scene_num}: {d['speaker']} — \"{text[:60]}...\"")
    
    output_path = output_dir / f"voice_scene_{scene_num}.mp3"
    
    # Run async TTS
    success = asyncio.run(_generate_tts(text, voice, output_path))
    
    if success:
        kb = output_path.stat().st_size / 1024
        logger.info(f"  ✅ Voice: {kb:.0f} KB")
        return output_path
    else:
        return None


def generate_all_voices(prompts: list[str], output_dir: Path) -> list[Path]:
    """
    Sabhi scenes ke voices generate karo.
    Returns: List of audio file paths
    """
    output_dir.mkdir(exist_ok=True)
    voices = []
    
    for i, prompt in enumerate(prompts, 1):
        if not prompt.strip():
            continue
        voice_path = generate_voice(prompt, i, output_dir)
        if voice_path:
            voices.append(voice_path)
    
    return voices
