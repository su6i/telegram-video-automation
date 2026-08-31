
import json
import time
import os
import sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

# Load environment to get base URL
from dotenv import load_dotenv
load_dotenv()

TARGET_URL = os.getenv("TARGET_SITE_BASE_URL", "https://example.com") + "/login"
COOKIES_FILE = "auth_cookies.json"

def main():
    print("🍪 Interactive Cookie Updater")
    print("----------------------------")
    print("This script will open a Chrome window.")
    print(f"1. Please login manually at: {TARGET_URL}")
    print("2. Once you are logged in and see the dashboard, come back here.")
    print("3. Press ENTER in this terminal to save the cookies.")
    print("----------------------------")

    chrome_options = Options()
    # No headless mode - we need the user to see the browser
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    
    # ⚠️ CRITICAL: MATCH SCRAPER USER AGENT EXACTLY
    # If this differs, Cloudflare will reject the cookies in the headless scraper.
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    chrome_options.add_argument(f"user-agent={ua}")

    # Attempt to keep window open
    chrome_options.add_experimental_option("detach", True)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        print(f"🌍 Opening {TARGET_URL}...")
        driver.get(TARGET_URL)
        
        # Wait for user
        input("\n⌨️  Press ENTER here after you have successfully logged in... ")
        
        # Capture cookies
        cookies = driver.get_cookies()
        
        if cookies:
            with open(COOKIES_FILE, "w") as f:
                json.dump(cookies, f, indent=2)
            print(f"✅ Success! {len(cookies)} cookies saved to {COOKIES_FILE}")
            print("You can now run the scraper.")
        else:
            print("⚠️  No cookies found! Did you close the browser?")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        print("Closing browser...")
        driver.quit()

if __name__ == "__main__":
    main()
