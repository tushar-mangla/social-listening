import os
from playwright.sync_api import sync_playwright

profile_dir = os.path.expanduser("~/.opencli/clis/chrome-profile")
with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=False,
        args=["--disable-blink-features=AutomationControlled"]
    )
    page = browser.pages[0] if browser.pages else browser.new_page()
    page.goto("https://www.facebook.com/")
    page.wait_for_timeout(3000)
    print("URL:", page.url)
    print("Has email input:", page.locator("input[name='email']").is_visible())
    browser.close()
