import asyncio
import sys
import os
from pathlib import Path
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def main():
    print("🔒 Google Account Login Helper")
    print("================================")
    
    async with async_playwright() as p:
        # Launch real Chrome browser on the system to avoid secure browser issues
        browser = await p.chromium.launch(
            headless=False,
            channel="chrome"
        )
        
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768}
        )
        page = await context.new_page()
        
        print("Opening Google Sign-in...")
        await page.goto("https://accounts.google.com/signin", wait_until="networkidle")
        
        print("\n👉 Please complete your login in the browser window.")
        print("👉 Make sure you are fully logged in and can see your account dashboard.")
        print("👉 CRITICAL: DO NOT close the browser window yourself!")
        print("\nOnce login is complete, come back here and press ENTER to save cookies...")
        
        input() # Wait for user to press enter
        
        try:
            cookies_file = Path("cookies.json")
            await context.storage_state(path=str(cookies_file))
            print(f"\n🎉 SUCCESS! Cookies saved to: {cookies_file.absolute()}")
        except Exception as e:
            print(f"\n❌ Error saving cookies: {e}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
