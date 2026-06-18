"""
tools/discover_selectors.py
────────────────────────────
Google Vids के UI selectors को discover करने का tool।

यह script Google Vids पर जाकर सभी interactive elements को
inspect करता है और उनके selectors print करता है।

Usage:
  python tools/discover_selectors.py

यह headless=False में run होगा ताकि आप देख सको।
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright

COOKIES_FILE = Path("cookies.json")

async def discover():
    print("🔍 Google Vids Selector Discovery Tool")
    print("=" * 50)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # देखना है
            slow_mo=500,
        )

        context_opts = {"viewport": {"width": 1366, "height": 768}}
        if COOKIES_FILE.exists():
            context_opts["storage_state"] = str(COOKIES_FILE)
            print("✅ Cookies loaded")

        context = await browser.new_context(**context_opts)
        page = await context.new_page()

        # Google Vids home
        print("\n📍 Navigating to Google Vids...")
        await page.goto("https://docs.google.com/videos", wait_until="networkidle")
        await asyncio.sleep(3)

        current_url = page.url
        print(f"Current URL: {current_url}")

        if "accounts.google.com" in current_url:
            print("\n⚠️  LOGIN REQUIRED!")
            print("Please login manually in the browser window...")
            print("Press Enter when done...")
            input()

            # Save cookies
            await context.storage_state(path=str(COOKIES_FILE))
            print("✅ Cookies saved to cookies.json")

        print("\n🔍 Discovering buttons and interactive elements...")
        
        # सभी buttons
        buttons = await page.query_selector_all('button, a[role="button"]')
        print(f"\n📋 Found {len(buttons)} buttons:")
        for i, btn in enumerate(buttons[:20]):
            text = await btn.inner_text()
            aria = await btn.get_attribute("aria-label") or ""
            cls  = await btn.get_attribute("class") or ""
            print(f"  [{i+1}] text='{text[:40]}' | aria='{aria[:40]}' | class='{cls[:50]}'")

        print("\n📋 Looking for 'New video' / 'Create' buttons specifically:")
        create_selectors = [
            'button:has-text("Blank video")',
            'button:has-text("New video")',
            'button:has-text("Create")',
            'a:has-text("New")',
        ]
        for sel in create_selectors:
            elem = await page.query_selector(sel)
            if elem:
                text = await elem.inner_text()
                print(f"  ✅ FOUND: '{sel}' → text: '{text}'")
            else:
                print(f"  ❌ Not found: '{sel}'")

        print("\n\n📸 Taking screenshot of current state...")
        await page.screenshot(path="logs/vids_discovery.png", full_page=True)
        print("✅ Screenshot saved: logs/vids_discovery.png")

        print("\n" + "=" * 50)
        print("Browser khula hua hai. Manually explore karein.")
        print("Kisi bhi element par right-click → Inspect karein")
        print("Press Enter to close browser...")
        input()

        await context.storage_state(path=str(COOKIES_FILE))
        print("✅ Final cookies saved")
        await browser.close()


if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)
    asyncio.run(discover())
