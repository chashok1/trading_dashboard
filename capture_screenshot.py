import asyncio
from playwright.async_api import async_playwright
import sys

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})
        await page.goto('http://127.0.0.1:8000/actionable')
        await page.wait_for_load_state('networkidle')

        # Wait a bit for data to render
        await page.wait_for_timeout(1000)

        # Take screenshot
        screenshot_path = 'actionable_screenshot.png'
        await page.screenshot(path=screenshot_path, full_page=False)
        print(f"Screenshot saved to {screenshot_path}")

        await browser.close()

asyncio.run(main())
