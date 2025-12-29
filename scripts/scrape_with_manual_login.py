#!/usr/bin/env python3
"""
Scrape Weekend Youtuber course structure after manual login
Waits for user to login, then scrapes the categories page
"""

import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

def scrape_after_login(login_url, target_url):
    """
    Open login page, wait for user to login, then scrape target page
    """
    
    # Setup Chrome driver with persistence
    options = webdriver.ChromeOptions()
    options.add_argument('--start-maximized')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
    # Disable headless so user can interact
    
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    
    try:
        print("=" * 80)
        print("🔓 OPENING LOGIN PAGE")
        print("=" * 80)
        print(f"\n📱 Opening: {login_url}\n")
        
        driver.get(login_url)
        
        print("⏳ WAITING FOR YOUR LOGIN...")
        print("   (Complete the login in the browser window)\n")
        print("   Checking every 5 seconds...\n")
        
        # Wait for user to login by checking if we're redirected or page changes
        # We'll check if we can reach the target page (categories)
        max_wait = 300  # 5 minutes
        check_interval = 5
        elapsed = 0
        
        while elapsed < max_wait:
            try:
                current_url = driver.current_url
                print(f"   Current URL: {current_url}")
                
                # Check if login was successful (URL changed or we're on target page)
                if "categories" in current_url or "dashboard" in current_url or "/products/" in current_url:
                    print("\n✅ LOGIN DETECTED!")
                    break
                
                # Try to navigate to target URL
                if elapsed % 10 == 0 and elapsed > 0:
                    print(f"\n   Trying to navigate to target page...")
                    driver.get(target_url)
                
                time.sleep(check_interval)
                elapsed += check_interval
                
            except Exception as e:
                time.sleep(check_interval)
                elapsed += check_interval
        
        print(f"\n✅ Proceeding to scrape content...\n")
        
        # Navigate to target URL
        driver.get(target_url)
        
        print("⏳ Waiting for page to fully load...")
        time.sleep(3)
        
        # Scroll down to trigger lazy loading
        print("📜 Scrolling to load all content...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        
        while True:
            # Scroll down
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            # Calculate new height
            new_height = driver.execute_script("return document.body.scrollHeight")
            
            if new_height == last_height:
                break
            last_height = new_height
        
        print("✅ All content loaded!")
        time.sleep(3)
        
        # Now scrape the page
        print("=" * 80)
        print("📚 SCRAPING COURSE STRUCTURE")
        print("=" * 80)
        
        html_content = driver.page_source
        
        # Save raw HTML for inspection
        html_file = "/Users/su6i/@-github/telegram-video-automation/.storage/weekend_youtuber_raw.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"\n✅ Raw HTML saved to: {html_file}")
        
        # Try to find course structure
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Look for sections
        print("\n📂 ANALYZING PAGE STRUCTURE...\n")
        
        # Try different selectors
        selectors_to_try = [
            ('h2', 'h2 tags'),
            ('h3', 'h3 tags'),
            ('.curriculum-section', '.curriculum-section'),
            ('.section', '.section class'),
            ('[class*="section"]', 'elements with "section" in class'),
            ('[class*="lesson"]', 'elements with "lesson" in class'),
        ]
        
        for selector, description in selectors_to_try:
            elements = soup.select(selector)
            if elements:
                print(f"Found {len(elements)} elements ({description}):")
                for i, elem in enumerate(elements[:10]):  # Show first 10
                    text = elem.get_text(strip=True)[:80]
                    print(f"  {i+1}. {text}")
                if len(elements) > 10:
                    print(f"  ... and {len(elements) - 10} more\n")
        
        print("\n" + "=" * 80)
        print("✅ SCRAPING COMPLETE")
        print("=" * 80)
        print(f"\nHTML file saved for manual analysis: {html_file}")
        print("You can now review the structure and tell me how to parse it.")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        print("\nKeeping browser open for 10 more seconds...")
        time.sleep(10)
        driver.quit()

def main():
    login_url = "https://www.contentcreator.com/login"
    target_url = "https://www.contentcreator.com/products/weekend-youtuber/categories"
    
    scrape_after_login(login_url, target_url)

if __name__ == "__main__":
    main()
