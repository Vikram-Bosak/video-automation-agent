"""
Google Colab Notebook: LTX-2.3 Video Generator
================================================
Free GPU se video generate karo!

Setup:
  1. Google Colab khole
  2. Runtime → Change runtime type → T4 GPU
  3. Yeh script paste karo ya notebook upload karo
  4. Run All

Requirements:
  - Google account (free)
  - T4 GPU (Colab free tier milta hai)
  - Google Sheet with prompts
"""

# ══════════════════════════════════════════════════════════════════════════════
# CELL 1: Install Dependencies
# ══════════════════════════════════════════════════════════════════════════════

!pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cu121
!pip install -q diffusers transformers accelerate safetensors
!pip install -q imageio[ffmpeg]
!pip install -q google-api-python-client google-auth google-auth-oauthlib
!pip install -q python-dotenv

print("✅ Dependencies installed!")

# ══════════════════════════════════════════════════════════════════════════════
# CELL 2: Mount Google Drive
# ══════════════════════════════════════════════════════════════════════════════

from google.colab import drive
drive.mount('/content/drive')

# Create output folder
import os
OUTPUT_DIR = "/content/drive/MyDrive/KidoBum_Videos"
os.makedirs(OUTPUT_DIR, exist_ok=True)
print(f"✅ Output folder: {OUTPUT_DIR}")

# ══════════════════════════════════════════════════════════════════════════════
# CELL 3: Check GPU
# ══════════════════════════════════════════════════════════════════════════════

import torch
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB")
else:
    print("❌ No GPU! Runtime → Change runtime type → T4 GPU select karo")

# ══════════════════════════════════════════════════════════════════════════════
# CELL 4: Google Sheets Setup
# ══════════════════════════════════════════════════════════════════════════════

# Service Account JSON upload karo (Colab file upload se)
from google.colab import files
import json, base64

print("📤 Service Account JSON upload karo:")
uploaded = files.upload()

creds_file = list(uploaded.keys())[0]
with open(creds_file, 'r') as f:
    creds_json = json.load(f)

print(f"✅ Credentials loaded: {creds_json.get('client_email', 'N/A')}")

# ══════════════════════════════════════════════════════════════════════════════
# CELL 5: Read Prompts from Google Sheet
# ══════════════════════════════════════════════════════════════════════════════

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_ID = "142Y0nesc8iQ2LQ8GFdWBtJCSKK8pCYkKHSlJobhMmhQ"
SHEET_NAME = "KidoBum_90Day_Prompts.csv"

creds = service_account.Credentials.from_service_account_info(creds_json, scopes=SCOPES)
service = build("sheets", "v4", credentials=creds)

def get_pending_row():
    """First pending/failed row dhundho."""
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_NAME}!A:I"
    ).execute()

    rows = result.get("values", [])
    if len(rows) < 2:
        return None

    header = rows[0]
    for idx, row in enumerate(rows[1:], start=2):
        status = row[7].strip().lower() if len(row) > 7 else ""
        title = row[2].strip() if len(row) > 2 else ""

        if not title:
            continue

        if status in ("", "pending") or "failed" in status:
            # Extract prompts (column G = index 6)
            prompts = []
            for r in rows[1:]:
                if len(r) > 6 and r[2].strip() == title:
                    prompt = r[6].strip()
                    if prompt:
                        prompts.append(prompt)

            return {
                "row_num": idx,
                "title": title,
                "day": row[0] if row else "",
                "prompts": prompts[:3],  # Max 3 prompts
            }

    return None

# Get pending row
pending = get_pending_row()
if pending:
    print(f"📋 Found: Day {pending['day']} | {pending['title']}")
    print(f"   Prompts: {len(pending['prompts'])}")
    for i, p in enumerate(pending['prompts'], 1):
        print(f"   P{i}: {p[:80]}...")
else:
    print("❌ No pending rows found!")

# ══════════════════════════════════════════════════════════════════════════════
# CELL 6: Load LTX-2.3 Model
# ══════════════════════════════════════════════════════════════════════════════

from diffusers import LTXPipeline
from diffusers.utils import export_to_video

print("📥 Loading LTX-2.3 (distilled)...")

# Distilled model: fast, 8GB VRAM ok
pipeline = LTXPipeline.from_pretrained(
    "Lightricks/LTX-Video",
    torch_dtype=torch.float16,
)
pipeline.to("cuda")

# Memory optimization
pipeline.enable_model_cpu_offload()
try:
    pipeline.enable_xformers_memory_efficient_attention()
    print("   xFormers enabled")
except:
    print("   xFormers not available (ok)")

print("✅ Model loaded!")

# ══════════════════════════════════════════════════════════════════════════════
# CELL 7: Generate Video
# ══════════════════════════════════════════════════════════════════════════════

import time

def generate_clip(prompt, clip_num, seed=42):
    """Ek 8-second clip generate karo."""
    print(f"\n🎥 Clip {clip_num}: Generating...")
    print(f"   Prompt: {prompt[:80]}...")

    t0 = time.time()

    output = pipeline(
        prompt=prompt,
        num_frames=192,          # 8s × 24fps
        num_inference_steps=8,    # Distilled: 8 steps
        guidance_scale=1.0,       # CFG=1 for distilled
        height=768,               # Portrait
        width=432,
        generator=torch.Generator("cuda").manual_seed(seed + clip_num),
    )

    elapsed = int(time.time() - t0)
    print(f"   ⏱️ Generated in {elapsed}s")

    # Save clip
    clip_path = f"/content/clip_{clip_num}.mp4"
    export_to_video(output.frames[0], clip_path, fps=24)

    # Free VRAM
    torch.cuda.empty_cache()

    return clip_path

# Generate clips
if pending and pending['prompts']:
    clips = []
    for i, prompt in enumerate(pending['prompts'], 1):
        clip = generate_clip(prompt, i)
        clips.append(clip)

    print(f"\n✅ {len(clips)} clips generated!")
else:
    print("❌ No prompts to generate!")
    clips = []

# ══════════════════════════════════════════════════════════════════════════════
# CELL 8: Join Clips into Final Video
# ══════════════════════════════════════════════════════════════════════════════

import subprocess

if clips:
    # Create concat file
    with open("/content/concat.txt", "w") as f:
        for c in clips:
            f.write(f"file '{c}'\n")

    # Join with FFmpeg
    output_name = pending['title'].replace(" ", "_").replace("'", "")[:50] + ".mp4"
    output_path = f"{OUTPUT_DIR}/{output_name}"

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", "/content/concat.txt",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        output_path,
    ]

    print(f"\n🎞️ Joining clips...")
    r = subprocess.run(cmd, capture_output=True, text=True)

    if r.returncode == 0:
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"✅ Video saved: {output_path}")
        print(f"   Size: {size_mb:.1f} MB")
        print(f"   Duration: {len(clips) * 8}s")
    else:
        print(f"❌ FFmpeg error: {r.stderr[-200:]}")

    # Cleanup temp clips
    for c in clips:
        os.remove(c)
else:
    print("❌ No clips to join!")

# ══════════════════════════════════════════════════════════════════════════════
# CELL 9: Update Google Sheet Status
# ══════════════════════════════════════════════════════════════════════════════

def mark_status(row_num, status, drive_link=""):
    """Sheet mein status update karo."""
    # Status column (H = 8th column)
    service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_NAME}!H{row_num}",
        valueInputOption="RAW",
        body={"values": [[status]]}
    ).execute()

    # Drive link column (I = 9th column)
    if drive_link:
        service.spreadsheets().values().update(
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_NAME}!I{row_num}",
            valueInputOption="RAW",
            body={"values": [[drive_link]]}
        ).execute()

if pending and clips:
    mark_status(pending['row_num'], "done", output_path)
    print(f"✅ Sheet updated: Row {pending['row_num']} → done")
else:
    print("⚠️ Sheet not updated (no video)")

# ══════════════════════════════════════════════════════════════════════════════
# CELL 10: Summary
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "="*50)
print("🎬 VIDEO GENERATION COMPLETE!")
print("="*50)
if pending:
    print(f"📅 Day: {pending['day']}")
    print(f"📝 Title: {pending['title']}")
    print(f"🎥 Clips: {len(clips)}")
    print(f"⏱️ Duration: {len(clips) * 8}s")
    print(f"📁 Output: {OUTPUT_DIR}/{output_name}")
print("="*50)
