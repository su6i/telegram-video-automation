
import time
import json
import os
import sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv

load_dotenv()

# Configuration
COOKIE_FILE = "auth_cookies.json"
BASE_URL = os.getenv("TARGET_SITE_BASE_URL")
if not BASE_URL:
    print("❌ Error: TARGET_SITE_BASE_URL not set in .env")
    sys.exit(1)

LOGIN_URL = os.getenv("TARGET_SITE_LOGIN_URL", f"{BASE_URL}/login")
TARGET_URL = f"{BASE_URL}/library" 

# Logging
def log(msg):
    print(msg)
    with open("auth_debug.log", "a") as f:
        f.write(msg + "\n")

log("Starting Auth Helper...")

chrome_options = Options()
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-gpu")
# chrome_options.add_argument("--user-data-dir=selenium_user_data") # Optional: persistence

try:
    log("Initializing Driver with WebDriverManager...")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
except Exception as e:
    log(f"Error starting driver with manager: {e}")
    try:
        log("Trying default WebDriver...")
        driver = webdriver.Chrome(options=chrome_options)
    except Exception as e2:
        log(f"Critical Error: Could not start any browser. {e2}")
        sys.exit(1)

target_url = TARGET_URL
login_url = LOGIN_URL

try:
    log("Opening Login Page...")
    driver.get(login_url)

    print("\n" + "="*50)
    print("PLEASE LOG IN MANUALLY IN THE BROWSER WINDOW.")
    print("Once you are logged in and can see the course content, come back here.")
    print("="*50 + "\n")

    input("Press ENTER here after you have successfully logged in and the course page is visible...")
    log("User pressed ENTER. Proceeding...")

    # Navigate specifically to target if not there
    if target_url not in driver.current_url:
        log(f"Navigating to course page: {target_url}")
        driver.get(target_url)
        time.sleep(5)

    log("Capturing Page Source and Cookies...")

    # Save HTML
    with open("debug_source.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    log("Saved debug_source.html")

    # Save Cookies
    cookies = driver.get_cookies()
    with open("content_creator_cookies.json", "w") as f:
        json.dump(cookies, f, indent=2)
    log("Saved content_creator_cookies.json")

    print("Success! Files saved.")

except Exception as e:
    log(f"An error occurred during execution: {e}")
finally:
    if 'driver' in locals():
        driver.quit()
        log("Driver closed.")
