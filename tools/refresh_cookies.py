#!/usr/bin/env python3
"""
Cookie Refresh Helper — Google Vids के लिए cookies export करने में मदद करता है।

Usage:
  1. Chrome में login करो accounts.google.com पर
  2. docs.google.com/videos खोलो
  3. EditThisCookie extension से cookies export करो (JSON format)
  4. File को cookies_raw.json में save करो
  5. यह script चलाओ: python tools/refresh_cookies.py
  6. Base64 encoded output को GOOGLE_COOKIES GitHub Secret में paste करो
"""

import json
import base64
import sys
from pathlib import Path

COOKIES_RAW = Path("cookies_raw.json")
COOKIES_OUTPUT = Path("cookies.json")

def validate_google_cookies(cookies: list[dict]) -> bool:
    """Check if cookies contain essential Google auth cookies."""
    essential_domains = ["google.com", "accounts.google.com"]
    essential_names = ["SID", "HSID", "SSID", "APISID", "SAPISID", "__Secure-1PSID", "__Secure-3PSID"]
    
    found_domains = set()
    found_names = set()
    
    for c in cookies:
        domain = c.get("domain", "")
        name = c.get("name", "")
        
        for ed in essential_domains:
            if ed in domain:
                found_domains.add(ed)
        
        if name in essential_names:
            found_names.add(name)
    
    print(f"\n📊 Cookie Analysis:")
    print(f"   Domains found: {found_domains}")
    print(f"   Auth cookies found: {len(found_names)}/{len(essential_names)}")
    print(f"   Names: {found_names}")
    
    missing_names = set(essential_names) - found_names
    if missing_names:
        print(f"   ⚠️  Missing: {missing_names}")
    
    has_auth = len(found_names) >= 4  # At least 4 essential cookies
    has_domain = "google.com" in found_domains
    
    return has_auth and has_domain


def main():
    print("=" * 60)
    print("  🍪 Google Vids Cookie Refresh Helper")
    print("=" * 60)
    
    if not COOKIES_RAW.exists():
        print(f"\n❌ {COOKIES_RAW} not found!")
        print("\nSteps to get cookies:")
        print("  1. Open Chrome → login to accounts.google.com")
        print("  2. Go to docs.google.com/videos")
        print("  3. Install 'EditThisCookie' or 'Cookie-Editor' extension")
        print("  4. Click extension icon → Export (JSON format)")
        print("  5. Save as cookies_raw.json in project root")
        print("  6. Run this script again: python tools/refresh_cookies.py")
        return 1
    
    try:
        with open(COOKIES_RAW) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in cookies_raw.json: {e}")
        return 1
    
    # Handle different export formats
    if isinstance(data, list):
        cookies = data
    elif isinstance(data, dict) and "cookies" in data:
        cookies = data["cookies"]
    else:
        print(f"❌ Unexpected format. Expected list or dict with 'cookies' key.")
        return 1
    
    print(f"\n📥 Found {len(cookies)} cookies in cookies_raw.json")
    
    if not validate_google_cookies(cookies):
        print("\n❌ Cookies don't contain essential Google auth tokens!")
        print("   Make sure you're logged in and exported from docs.google.com/videos")
        return 1
    
    # Save as Playwright storage state format
    storage_state = {
        "cookies": cookies,
        "origins": []
    }
    
    with open(COOKIES_OUTPUT, "w") as f:
        json.dump(storage_state, f, indent=2)
    
    print(f"\n✅ cookies.json updated! ({len(cookies)} cookies)")
    
    # Generate base64 for GitHub Secret
    with open(COOKIES_OUTPUT, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    
    b64_file = Path("cookies_base64.txt")
    with open(b64_file, "w") as f:
        f.write(b64)
    
    print(f"📦 Base64 output: {b64_file}")
    print(f"\n🔄 To update GitHub Secret:")
    print(f"   gh secret set GOOGLE_COOKIES -r Vikram-Bosak/video-automation-agent < {b64_file}")
    print(f"\n   OR manually copy contents of {b64_file} to GitHub Secret GOOGLE_COOKIES")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
