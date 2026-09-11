import os
from playwright.sync_api import sync_playwright

state_file = os.path.abspath("facebook_state.json")

def login():
    print("Launching browser for Facebook login...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chrome", args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.facebook.com/")
        
        print("Please log in to Facebook in the opened browser window.")
        print("Waiting for feed to load...")
        
        # Wait for the user to login and the feed to appear
        page.wait_for_selector('[role="feed"], [role="main"], [aria-label="Create a post"]', timeout=300000) # 5 minutes to login
        
        print("Login successful! Saving session state...")
        context.storage_state(path=state_file)
        print(f"Session saved to {state_file}")
        browser.close()

if __name__ == "__main__":
    login()
